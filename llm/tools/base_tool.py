"""
Base Tool Class for RCA Analysis Tools

Provides abstract interface for all RCA analysis tools.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import time
import logging

from models.tool_results import ToolResult
from rag_manager import RAGManager

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """
    Abstract base class for all RCA analysis tools.
    
    All tools must implement the analyze() method and follow
    the standard interface for consistency.
    """
    
    def __init__(
        self,
        llm_adapter: Any,
        rag_manager: RAGManager,
        tool_name: str
    ):
        """
        Initialize the tool.
        
        Args:
            llm_adapter: LLM adapter (Gemini, Azure OpenAI, etc.)
            rag_manager: RAG manager for document retrieval
            tool_name: Name of this tool
        """
        self.llm_adapter = llm_adapter
        self.rag = rag_manager
        self.tool_name = tool_name
        self.logger = logging.getLogger(f"{__name__}.{tool_name}")
    
    @abstractmethod
    async def analyze(
        self,
        failure_description: str,
        equipment_name: str,
        symptoms: List[str],
        **kwargs
    ) -> ToolResult:
        """
        Perform RCA analysis.
        
        Args:
            failure_description: Description of the failure
            equipment_name: Name of the equipment that failed
            symptoms: List of observed symptoms
            **kwargs: Additional tool-specific parameters
            
        Returns:
            ToolResult containing analysis results
        """
        pass
    
    async def _retrieve_context(
        self,
        equipment_name: str,
        symptoms: List[str],
        top_k: int = 5
    ) -> List[Any]:
        """
        Retrieve relevant context from RAG.
        
        Args:
            equipment_name: Equipment name
            symptoms: Failure symptoms
            top_k: Number of documents to retrieve
            
        Returns:
            List of retrieved documents
        """
        try:
            docs = await self.rag.retrieve_equipment_context(
                equipment_name=equipment_name,
                failure_symptoms=symptoms,
                top_k=top_k
            )
            self.logger.info(f"Retrieved {len(docs)} documents from RAG")
            return docs
        except Exception as e:
            self.logger.error(f"Error retrieving RAG context: {e}")
            return []
    
    def _format_context(self, documents: List[Any]) -> str:
        """
        Format retrieved documents for LLM context.
        
        Args:
            documents: List of Document objects from RAG
            
        Returns:
            Formatted string for LLM prompt
        """
        if not documents:
            return "No relevant documentation found."
        
        context_parts = []
        for i, doc in enumerate(documents, 1):
            # Get source document name (e.g., "Rotary Kiln_Hongda_OEM Manual")
            source = doc.source if hasattr(doc, 'source') else 'Unknown'
            content = doc.content if hasattr(doc, 'content') else str(doc)
            
            # Use document name instead of number for better user understanding
            context_parts.append(
                f"[{source}]\n"
                f"{content}\n"
            )
        
        return "\n---\n".join(context_parts)
    
    async def _execute_with_timing(
        self,
        analysis_func,
        *args,
        **kwargs
    ) -> ToolResult:
        """
        Execute analysis function with timing and error handling.
        
        Args:
            analysis_func: Async function to execute
            *args, **kwargs: Arguments for the function
            
        Returns:
            ToolResult with execution metrics
        """
        start_time = time.time()
        
        try:
            result = await analysis_func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            # Get LLM stats if available
            tokens_used = 0
            cost_usd = 0.0
            if hasattr(self.llm_adapter, 'get_stats'):
                stats = self.llm_adapter.get_stats()
                tokens_used = stats.get('total_tokens', 0)
                cost_usd = stats.get('total_cost_usd', 0.0)
            
            return ToolResult(
                tool_name=self.tool_name,
                success=True,
                result=result,
                error=None,
                execution_time_seconds=execution_time,
                tokens_used=tokens_used,
                cost_usd=cost_usd
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Tool execution failed: {e}", exc_info=True)
            
            return ToolResult(
                tool_name=self.tool_name,
                success=False,
                result={},
                error=str(e),
                execution_time_seconds=execution_time,
                tokens_used=0,
                cost_usd=0.0
            )
