"""
History Matcher — queries Neo4j knowledge graph for similar past incidents.

Used by IntegratedRCATool at the start of every RCA to surface verified
historical root causes and CAPA actions from plant records.

Design:
  - Model is loaded ONCE (lazy, on first call) and reused for all requests.
  - All blocking Neo4j + numpy work runs in asyncio.to_thread so the async
    pipeline is never blocked.
  - If Neo4j is unreachable or query fails → returns ([], "") silently.
    The RCA pipeline continues without history — never crashes.
"""

import os
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "rcapassword")

EMBEDDING_MODEL   = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_TOP_K     = 3
DEFAULT_THRESHOLD = 0.65

# Module-level singleton — loaded on first call, reused forever
_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"[HistoryMatcher] Loading embedding model: {EMBEDDING_MODEL}")
        _model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("[HistoryMatcher] Embedding model ready.")
    return _model


# ── Synchronous core (runs in thread) ────────────────────────────────────────

def _query_sync(
    equipment_name: str,
    problem_description: str,
    top_k: int,
    min_similarity: float,
) -> list:
    """
    Embed the query, fetch all incident embeddings from Neo4j,
    compute cosine similarities, return top-k above threshold.
    """
    import numpy as np
    from neo4j import GraphDatabase

    model = _get_model()
    query_text = f"Equipment: {equipment_name}. Problem: {problem_description}"
    query_vec  = model.encode(query_text, normalize_embeddings=True).astype("float32")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD), connection_timeout=3.0)
    try:
        with driver.session() as session:
            rows = session.run("""
                MATCH (i:Incident)
                WHERE i.embedding IS NOT NULL
                OPTIONAL MATCH (i)-[:HAS_CAPA]->(c:CAPA)
                    WHERE c.type = 'corrective' OR c.type IS NULL
                OPTIONAL MATCH (i)-[:INVESTIGATED_BY]->(p:Person)
                RETURN i,
                       collect(DISTINCT {
                           action:         c.action,
                           responsibility: c.responsibility,
                           target_date:    c.target_date,
                           idx:            c.capa_index
                       }) AS capa_list,
                       collect(DISTINCT p.name) AS team_members
            """)

            incidents = []
            for row in rows:
                node     = dict(row["i"])
                capa_raw = row["capa_list"]
                team     = [n for n in (row["team_members"] or []) if n]
                capa = sorted(
                    [c for c in capa_raw if c.get("action")],
                    key=lambda x: x.get("idx") or 0,
                )
                incidents.append((
                    node,
                    [{k: v for k, v in c.items() if k != "idx"} for c in capa],
                    team,
                ))

        if not incidents:
            return []

        # Cosine similarity (vectors are pre-normalised → dot product)
        emb_matrix = __import__("numpy").array(
            [inc[0]["embedding"] for inc in incidents], dtype="float32"
        )
        scores = emb_matrix @ query_vec
        ranked = sorted(zip(scores, incidents), key=lambda x: x[0], reverse=True)

        results = []
        for score, (node, capa, team) in ranked[:top_k]:
            if float(score) < min_similarity:
                break
            results.append({
                "source_file":       node.get("source_file", ""),
                "plant":             node.get("plant", ""),
                "department":        node.get("department", ""),
                "equipment":         node.get("equipment", ""),
                "occurrence_from":   node.get("occurrence_from"),
                "downtime_minutes":  node.get("downtime_minutes"),
                "problem_statement": node.get("problem_statement", ""),
                "root_cause":        node.get("root_cause", ""),
                "capa":              capa,
                "team_members":      team,
                "similarity_score":  round(float(score), 4),
            })
        return results

    finally:
        driver.close()


def _format_for_prompt(matches: list) -> str:
    """Format match list as a HISTORICAL REFERENCE block for LLM prompt injection."""
    if not matches:
        return ""
    lines = [
        "━━━ HISTORICAL REFERENCE (Verified plant records) ━━━",
        "Similar incidents from the plant knowledge base. Use as REFERENCE only —",
        "validate against current symptoms before drawing conclusions.",
        "",
    ]
    for i, m in enumerate(matches, 1):
        pct = round(m["similarity_score"] * 100)
        lines.append(f"[Reference {i} — {pct}% similarity]")
        lines.append(f"  Plant / Equipment : {m['plant']} — {m['equipment']}")
        lines.append(f"  Date              : {m['occurrence_from'] or 'Unknown'}")
        lines.append(f"  Downtime          : {m['downtime_minutes'] or '?'} minutes")
        lines.append(f"  Problem           : {m['problem_statement']}")
        lines.append(f"  Root Cause Found  : {m['root_cause']}")
        capa = m.get("capa") or []
        if capa:
            lines.append("  Actions Taken     :")
            for c in capa[:3]:
                owner = f" [{c['responsibility']}]" if c.get("responsibility") else ""
                lines.append(f"    • {c['action']}{owner}")
        lines.append("")
    lines.append("━━━ END HISTORICAL REFERENCE ━━━")
    return "\n".join(lines)


# ── Public async API ──────────────────────────────────────────────────────────

async def find_and_format(
    equipment_name: str,
    problem_description: str,
    top_k: int = DEFAULT_TOP_K,
    min_similarity: float = DEFAULT_THRESHOLD,
) -> tuple:
    """
    Query historical incidents and return serialisable results + prompt text.

    Returns:
        (matches: list[dict], prompt_text: str)
        Both empty if Neo4j unavailable or no matches above threshold.
    """
    try:
        matches = await asyncio.to_thread(
            _query_sync, equipment_name, problem_description, top_k, min_similarity
        )
        return matches, _format_for_prompt(matches)
    except Exception as exc:
        logger.warning(f"[HistoryMatcher] History lookup skipped: {exc}")
        return [], ""
