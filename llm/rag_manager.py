"""
RAG Manager for RCA System

Handles retrieval of relevant information from Weaviate vector database.
Integrates with existing PDF ingestion pipeline.
"""

import os
import json
import asyncio
import logging
import functools
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

try:
    import weaviate
    from weaviate.classes.query import MetadataQuery
    from weaviate.exceptions import WeaviateQueryError
except ImportError:
    weaviate = None
    WeaviateQueryError = Exception

logger = logging.getLogger(__name__)


@dataclass
class Document:
    """Retrieved document from RAG."""
    content: str
    source: str
    score: float
    metadata: Dict[str, Any]


class RAGManager:
    """
    Manages retrieval from Weaviate vector database.
    
    Provides context-aware retrieval for RCA analysis.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize RAG manager.
        
        Args:
            config_path: Path to weaviate_config.json (defaults to data_ingestion/weaviate_config.json)
        """
        if weaviate is None:
            raise ImportError("weaviate-client not installed. Run: pip install weaviate-client")
        
        # Default config path
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data_ingestion",
                "weaviate_config.json"
            )
        
        self.config = self._load_config(config_path)
        self.client = None
        self.collection_name = self.config["collection"]["name"]
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """
        Build Weaviate config, preferring environment variables over JSON file.

        Priority:
          1. Environment variables (WEAVIATE_URL, WEAVIATE_API_KEY, ...) — used in Docker
          2. weaviate_config.json — fallback for local development only

        This means the container never crashes on a missing JSON file.
        """
        # Try loading .env for local dev (silently ignored if file doesn't exist)
        from dotenv import load_dotenv
        llm_dir = os.path.dirname(__file__)
        load_dotenv(os.path.join(llm_dir, ".env"))

        weaviate_url = os.getenv("WEAVIATE_URL")
        weaviate_api_key = os.getenv("WEAVIATE_API_KEY")
        hf_api_key = os.getenv("HUGGINGFACE_API_KEY", "")

        # ── Production path: env vars present → build config dict directly ──
        if weaviate_url and weaviate_api_key:
            logger.info("Weaviate config loaded from environment variables")
            return {
                "weaviate": {
                    "url": weaviate_url,
                    "api_key": weaviate_api_key,
                },
                "collection": {
                    "name": os.getenv("WEAVIATE_COLLECTION", "Rca"),
                },
                "embedding": {
                    "huggingface_api_key": hf_api_key,
                },
            }

        # ── Local dev fallback: load from JSON and overlay any env vars ──
        logger.info(f"WEAVIATE_URL not set — falling back to JSON config: {config_path}")
        if not os.path.exists(config_path):
            raise FileNotFoundError(
                f"Weaviate config not found at '{config_path}' "
                "and WEAVIATE_URL/WEAVIATE_API_KEY env vars are not set. "
                "Set the env vars (recommended) or provide a weaviate_config.json."
            )

        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        # Overlay any partial env vars on top of the JSON values
        if weaviate_url:
            cfg["weaviate"]["url"] = weaviate_url
        if weaviate_api_key:
            cfg["weaviate"]["api_key"] = weaviate_api_key
        if hf_api_key:
            cfg["embedding"]["huggingface_api_key"] = hf_api_key

        return cfg
    
    def connect(self):
        """Connect to Weaviate Cloud."""
        if self.client is not None:
            logger.info("Already connected to Weaviate")
            return
        
        logger.info(f"Connecting to Weaviate at {self.config['weaviate']['url']}")
        
        try:
            # Use Weaviate v4 connection method with Auth class
            from weaviate.classes.init import Auth, AdditionalConfig, Timeout

            self.client = weaviate.connect_to_weaviate_cloud(
                cluster_url=self.config["weaviate"]["url"],
                auth_credentials=Auth.api_key(self.config["weaviate"]["api_key"]),
                skip_init_checks=True,
                additional_config=AdditionalConfig(
                    timeout=Timeout(init=10, query=15, insert=120)  # fail fast on stale gRPC
                ),
            )
            
            # Verify connection by checking if client is ready
            if self.client.is_ready():
                logger.info("Successfully connected to Weaviate")
                
                # Check if collection exists
                try:
                    # Try with capital P first (Weaviate auto-capitalizes collection names)
                    collection = self.client.collections.get("Rca")
                    logger.info(f"Collection 'Rca' found")
                    
                    # Update collection name to match what exists
                    self.collection_name = "Rca"
                    
                except Exception as e:
                    logger.warning(f"Collection 'Rca' not found, trying lowercase: {e}")
                    try:
                        collection = self.client.collections.get("rca")
                        logger.info(f"Collection 'rca' found")
                        self.collection_name = "rca"
                    except Exception as e2:
                        logger.warning(f"Collection '{self.collection_name}' not found: {e2}")
                        logger.warning("You may need to run the PDF ingestion first to create the collection")
            else:
                logger.error("Connected to Weaviate but client is not ready")
                
        except Exception as e:
            logger.error(f"Failed to connect to Weaviate: {e}")
            raise
    
    def disconnect(self):
        """Disconnect from Weaviate."""
        if self.client:
            self.client.close()
            self.client = None
            logger.info("Disconnected from Weaviate")

    def _reconnect(self):
        """Close stale client and reconnect (called when gRPC channel is dead)."""
        logger.info("Reconnecting to Weaviate after stale connection...")
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass
        self.client = None
        self.connect()

    async def _query_bm25(
        self,
        query_text: str,
        limit: int,
        timeout: float = 12.0,
    ):
        """
        Run a BM25 query in a thread executor so it doesn't block the event loop,
        and cap it with asyncio.wait_for so a hung gRPC call fails fast.

        Retries once with a fresh connection if the first attempt fails.
        """
        for attempt in range(2):  # try twice: once normally, once after reconnect
            try:
                collection = self.client.collections.get(self.collection_name)

                def _run():
                    return collection.query.bm25(query=query_text, limit=limit)

                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, _run),
                    timeout=timeout,
                )
                return result

            except asyncio.TimeoutError:
                logger.warning(
                    f"Weaviate BM25 query timed out after {timeout}s "
                    f"(attempt {attempt + 1}/2). "
                    + ("Giving up — continuing without RAG context." if attempt else "Reconnecting...")
                )
                if attempt == 0:
                    self._reconnect()
                else:
                    return None

            except Exception as e:
                logger.warning(
                    f"Weaviate BM25 query failed (attempt {attempt + 1}/2): {e}. "
                    + ("Giving up." if attempt else "Reconnecting...")
                )
                if attempt == 0:
                    self._reconnect()
                else:
                    return None

        return None
    
    async def retrieve_equipment_context(
        self,
        equipment_name: str,
        failure_symptoms: List[str],
        top_k: int = 10
    ) -> List[Document]:
        """
        Retrieve relevant equipment context from manuals.
        
        Args:
            equipment_name: Name of the equipment (e.g., "Rotary Kiln")
            failure_symptoms: List of observed symptoms
            top_k: Number of documents to retrieve
            
        Returns:
            List of relevant documents
        """
        if self.client is None:
            self.connect()
        
        # Build query combining equipment name and symptoms
        query_text = f"{equipment_name} {' '.join(failure_symptoms)}"
        
        logger.info(f"Retrieving context for: {query_text}")
        
        try:
            response = await self._query_bm25(query_text, limit=top_k)
            if response is None:
                return []  # timed out or failed — analysis continues without RAG

            documents = []
            for obj in response.objects:
                # Use sourcePdf as source since that's the actual property name
                doc = Document(
                    content=obj.properties.get("content", ""),
                    source=obj.properties.get("sourcePdf", "Unknown"),
                    score=obj.metadata.score if hasattr(obj.metadata, 'score') and obj.metadata.score else 0.5,
                    metadata={
                        "page": obj.properties.get("pageNumber"),
                        "chunk_type": obj.properties.get("chunkType"),
                        "source_folder": obj.properties.get("sourceFolder"),
                    }
                )
                documents.append(doc)
            
            logger.info(f"Retrieved {len(documents)} documents")
            return documents
            
        except Exception as e:
            logger.error(f"Error retrieving equipment context: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def retrieve_troubleshooting_guides(
        self,
        equipment_name: str,
        error_code: Optional[str] = None,
        top_k: int = 5
    ) -> List[Document]:
        """
        Retrieve troubleshooting procedures from manuals.
        
        Args:
            equipment_name: Name of the equipment
            error_code: Optional error code to search for
            top_k: Number of documents to retrieve
            
        Returns:
            List of troubleshooting documents
        """
        if self.client is None:
            self.connect()
        
        # Build query for troubleshooting
        query_parts = [equipment_name, "troubleshooting", "problem", "solution"]
        if error_code:
            query_parts.append(error_code)
        
        query_text = " ".join(query_parts)
        logger.info(f"Retrieving troubleshooting guides for: {query_text}")
        
        try:
            response = await self._query_bm25(query_text, limit=top_k)
            if response is None:
                return []

            documents = []
            for obj in response.objects:
                doc = Document(
                    content=obj.properties.get("content", ""),
                    source=obj.properties.get("sourcePdf", "Unknown"),
                    score=obj.metadata.score if hasattr(obj.metadata, 'score') and obj.metadata.score else 0.5,
                    metadata={
                        "page": obj.properties.get("pageNumber"),
                        "chunk_type": obj.properties.get("chunkType"),
                    }
                )
                documents.append(doc)

            return documents

        except Exception as e:
            logger.error(f"Error retrieving troubleshooting guides: {e}")
            return []
    
    async def retrieve_maintenance_procedures(
        self,
        equipment_name: str,
        component: Optional[str] = None,
        top_k: int = 5
    ) -> List[Document]:
        """
        Retrieve maintenance procedures from manuals.
        
        Args:
            equipment_name: Name of the equipment
            component: Specific component (e.g., "bearing", "motor")
            top_k: Number of documents to retrieve
            
        Returns:
            List of maintenance procedure documents
        """
        if self.client is None:
            self.connect()
        
        query_parts = [equipment_name, "maintenance", "procedure", "service"]
        if component:
            query_parts.append(component)
        
        query_text = " ".join(query_parts)
        logger.info(f"Retrieving maintenance procedures for: {query_text}")
        
        try:
            response = await self._query_bm25(query_text, limit=top_k)
            if response is None:
                return []

            documents = []
            for obj in response.objects:
                doc = Document(
                    content=obj.properties.get("content", ""),
                    source=obj.properties.get("sourcePdf", "Unknown"),
                    score=obj.metadata.score if hasattr(obj.metadata, 'score') and obj.metadata.score else 0.5,
                    metadata={
                        "page": obj.properties.get("pageNumber"),
                        "chunk_type": obj.properties.get("chunkType"),
                    }
                )
                documents.append(doc)

            return documents

        except Exception as e:
            logger.error(f"Error retrieving maintenance procedures: {e}")
            return []
    
    def format_context_for_llm(self, documents: List[Document]) -> str:
        """
        Format retrieved documents for LLM context.
        
        Args:
            documents: List of retrieved documents
            
        Returns:
            Formatted string for LLM prompt
        """
        if not documents:
            return "No relevant documentation found."
        
        context_parts = []
        for i, doc in enumerate(documents, 1):
            source_info = f"Source: {doc.source}"
            if doc.metadata.get("page"):
                source_info += f", Page: {doc.metadata['page']}"
            
            context_parts.append(
                f"[Document {i}] (Relevance: {doc.score:.2f})\n"
                f"{source_info}\n"
                f"{doc.content}\n"
            )
        
        return "\n---\n".join(context_parts)
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
