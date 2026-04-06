"""
Phase 2: Build Neo4j Knowledge Graph from extracted RCA history.

Reads output/extracted_data.json → creates nodes and relationships in Neo4j
→ generates and stores sentence embeddings on each Incident node.

Idempotent: safe to re-run. Uses MERGE so existing nodes are updated, not duplicated.

Usage:
    pip install -r requirements_ingestion.txt
    python build_knowledge_graph.py

Environment variables (reads from llm/.env automatically):
    NEO4J_URI      bolt://localhost:7687  (default — local Docker-exposed port)
    NEO4J_USER     neo4j                  (default)
    NEO4J_PASSWORD rcapassword            (default)
"""

import json
import re
import os
import sys
import logging
from pathlib import Path

from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
LLM_DIR = SCRIPT_DIR.parent.parent / "llm"

try:
    from dotenv import load_dotenv
    load_dotenv(LLM_DIR / ".env")
except ImportError:
    pass

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "rcapassword")

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
OUTPUT_FILE     = SCRIPT_DIR / "output" / "extracted_data.json"

# Fields to copy directly onto the Incident node
INCIDENT_SCALAR_FIELDS = [
    "occurrence_from", "occurrence_to", "downtime_minutes",
    "problem_statement", "root_cause", "impact_on_production",
    "pm_frequency", "opportunity_loss", "pages_extracted",
    "proof_images_description",
]


# ── Normalisation ─────────────────────────────────────────────────────────────

def plant_from_record(record: dict) -> str:
    """Use source_file prefix as authoritative plant name (CPP1/CPP2)."""
    src = record.get("source_file", "")
    if src.startswith("CPP1/"):
        return "CPP1"
    if src.startswith("CPP2/"):
        return "CPP2"
    return (record.get("plant") or "Unknown").strip()


def normalize_name(name: str) -> str:
    """Lowercase, strip, collapse whitespace — used as merge key for Equipment."""
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def make_embedding_text(record: dict) -> str:
    """Text to embed for similarity search: equipment + problem + root cause."""
    equipment = (record.get("equipment") or "").strip()
    problem   = (record.get("problem_statement") or "").strip()
    root      = (record.get("root_cause") or "").strip()
    parts = []
    if equipment:
        parts.append(f"Equipment: {equipment}")
    if problem:
        parts.append(f"Problem: {problem}")
    if root:
        parts.append(f"Root Cause: {root}")
    return ". ".join(parts)


# ── Schema ────────────────────────────────────────────────────────────────────

def setup_schema(session) -> None:
    """Create uniqueness constraints (idempotent)."""
    constraints = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Plant)      REQUIRE n.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Department)  REQUIRE n.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Equipment)   REQUIRE n.normalized_name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Incident)    REQUIRE n.source_file IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Person)      REQUIRE n.name IS UNIQUE",
    ]
    for cypher in constraints:
        session.run(cypher)
    logger.info("Schema constraints ready.")


# ── Ingestion ─────────────────────────────────────────────────────────────────

def ingest_record(session, record: dict, embedding: list) -> None:
    source_file = record["source_file"]
    plant       = plant_from_record(record)
    dept        = (record.get("department") or "Unknown").strip()
    equip       = (record.get("equipment")  or "Unknown").strip()
    equip_norm  = normalize_name(equip)

    # ── Nodes ──────────────────────────────────────────────────────────────
    session.run("MERGE (:Plant {name: $name})",      name=plant)
    session.run("MERGE (:Department {name: $name})", name=dept)
    session.run(
        "MERGE (e:Equipment {normalized_name: $norm}) SET e.name = $name",
        norm=equip_norm, name=equip,
    )

    # Build Incident props
    props = {k: record.get(k) for k in INCIDENT_SCALAR_FIELDS}
    props.update({
        "source_file":            source_file,
        "plant":                  plant,
        "department":             dept,
        "equipment":              equip,
        "embedding":              embedding,
        # Store list fields as JSON strings (Neo4j doesn't support nested objects)
        "chronology_of_events":   json.dumps(record.get("chronology_of_events")   or []),
        "observations_from_site": json.dumps(record.get("observations_from_site") or []),
        "breakdown_history":      json.dumps(record.get("breakdown_history_6months") or []),
    })
    session.run(
        "MERGE (i:Incident {source_file: $source_file}) SET i += $props",
        source_file=source_file, props=props,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    rels = [
        # Equipment → Incident
        """MATCH (e:Equipment {normalized_name: $equip_norm}), (i:Incident {source_file: $sf})
           MERGE (e)-[:HAD_INCIDENT]->(i)""",
        # Incident → Plant
        """MATCH (p:Plant {name: $plant}),      (i:Incident {source_file: $sf})
           MERGE (i)-[:AT_PLANT]->(p)""",
        # Incident → Department
        """MATCH (d:Department {name: $dept}),  (i:Incident {source_file: $sf})
           MERGE (i)-[:IN_DEPARTMENT]->(d)""",
        # Equipment → Department
        """MATCH (e:Equipment {normalized_name: $equip_norm}), (d:Department {name: $dept})
           MERGE (e)-[:IN_DEPARTMENT]->(d)""",
    ]
    for cypher in rels:
        session.run(cypher, sf=source_file, equip_norm=equip_norm, plant=plant, dept=dept)

    # ── WhySteps ───────────────────────────────────────────────────────────
    for ws in (record.get("why_steps") or []):
        if not (ws.get("question") or ws.get("answer")):
            continue
        session.run(
            """MERGE (w:WhyStep {source_file: $sf, step_number: $step})
               SET w.question = $q, w.answer = $a
               WITH w
               MATCH (i:Incident {source_file: $sf})
               MERGE (i)-[:HAS_WHY_STEP]->(w)""",
            sf=source_file,
            step=ws.get("step", 0),
            q=(ws.get("question") or ""),
            a=(ws.get("answer")   or ""),
        )

    # ── CAPA (corrective + preventive) ─────────────────────────────────────
    capa_list = [(record.get("capa") or [], "corrective", 0),
                 (record.get("preventive_actions") or [], "preventive", 1000)]
    for items, capa_type, offset in capa_list:
        for idx, item in enumerate(items):
            action = (item.get("action") or "").strip()
            if not action:
                continue
            session.run(
                """MERGE (c:CAPA {source_file: $sf, capa_index: $idx})
                   SET c.action = $action, c.responsibility = $resp,
                       c.target_date = $target, c.status = $status, c.type = $type
                   WITH c
                   MATCH (i:Incident {source_file: $sf})
                   MERGE (i)-[:HAS_CAPA]->(c)""",
                sf=source_file,
                idx=offset + idx,
                action=action,
                resp=item.get("responsibility"),
                target=item.get("target_date"),
                status=item.get("status"),
                type=capa_type,
            )

    # ── Team Members ───────────────────────────────────────────────────────
    for member in (record.get("team_members") or []):
        name = (member or "").strip()
        if not name:
            continue
        session.run(
            """MERGE (p:Person {name: $name})
               WITH p
               MATCH (i:Incident {source_file: $sf})
               MERGE (i)-[:INVESTIGATED_BY]->(p)""",
            name=name, sf=source_file,
        )


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary(session) -> None:
    print("\n── Knowledge Graph Summary ─────────────────────────────")
    rows = session.run(
        "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt ORDER BY cnt DESC"
    )
    for r in rows:
        print(f"  {r['label']:<20} {r['cnt']:>4} nodes")

    print()
    rows = session.run(
        "MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS cnt ORDER BY cnt DESC"
    )
    for r in rows:
        print(f"  {r['rel']:<25} {r['cnt']:>4} relationships")
    print("────────────────────────────────────────────────────────\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not OUTPUT_FILE.exists():
        logger.error(f"Extracted data not found: {OUTPUT_FILE}")
        logger.error("Run extract_rca_history.py first.")
        sys.exit(1)

    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)
    logger.info(f"Loaded {len(records)} records from {OUTPUT_FILE.name}")

    # Generate embeddings for all records upfront
    logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
    logger.info("(First run downloads ~80 MB from HuggingFace — cached for future runs)")
    model = SentenceTransformer(EMBEDDING_MODEL)

    texts = [make_embedding_text(r) for r in records]
    logger.info(f"Generating {len(texts)} embeddings...")
    embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
    logger.info(f"Embeddings ready — shape: {embeddings.shape}")

    # Connect and populate Neo4j
    logger.info(f"Connecting to Neo4j at {NEO4J_URI} ...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    logger.info("Connected.")

    with driver.session() as session:
        setup_schema(session)
        for i, (record, emb) in enumerate(zip(records, embeddings)):
            src = record.get("source_file", f"record_{i}")
            logger.info(f"  [{i+1:>2}/{len(records)}] {src}")
            ingest_record(session, record, emb.tolist())
        print_summary(session)

    driver.close()
    logger.info("Done. Knowledge graph built successfully.")
    logger.info(f"Neo4j browser: http://localhost:7474")


if __name__ == "__main__":
    main()
