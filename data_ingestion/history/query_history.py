"""
Phase 2: Semantic similarity search over the historical RCA knowledge graph.

Used as a module by the LLM pipeline (Phase 3) and directly as a CLI for testing.

How it works:
  1. Embeds the query (equipment + problem description) with the same model used
     during ingestion (all-MiniLM-L6-v2).
  2. Fetches all Incident embeddings from Neo4j in one query.
  3. Computes cosine similarity client-side (vectors are pre-normalized).
  4. Returns top-k matches above the similarity threshold, with CAPA and team info.

CLI usage:
    python query_history.py "Coal crusher" "Bearing seized, high vibration"
    python query_history.py "15MW Gen CB" "CB trip due to under voltage" --top 5 --threshold 0.5
"""

import json
import os
import sys
import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer

# ── Config ────────────────────────────────────────────────────────────────────

try:
    from dotenv import load_dotenv
    _LLM_DIR = Path(__file__).resolve().parent.parent.parent / "llm"
    load_dotenv(_LLM_DIR / ".env")
except ImportError:
    pass

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "rcapassword")

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

logger = logging.getLogger(__name__)

# Lazy-loaded model — avoids reloading on each call when used as a module
_model: Optional[SentenceTransformer] = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class HistoricalMatch:
    source_file:       str
    plant:             str
    department:        str
    equipment:         str
    occurrence_from:   Optional[str]
    downtime_minutes:  Optional[int]
    problem_statement: str
    root_cause:        str
    capa:              list = field(default_factory=list)
    team_members:      list = field(default_factory=list)
    similarity_score:  float = 0.0

    def to_dict(self) -> dict:
        return {
            "source_file":       self.source_file,
            "plant":             self.plant,
            "department":        self.department,
            "equipment":         self.equipment,
            "occurrence_from":   self.occurrence_from,
            "downtime_minutes":  self.downtime_minutes,
            "problem_statement": self.problem_statement,
            "root_cause":        self.root_cause,
            "capa":              self.capa,
            "team_members":      self.team_members,
            "similarity_score":  round(self.similarity_score, 4),
        }


# ── Core query ────────────────────────────────────────────────────────────────

def find_similar_incidents(
    equipment_name:    str,
    problem_description: str,
    root_cause_hint:   str  = "",
    top_k:             int  = 3,
    min_similarity:    float = 0.65,
) -> list[HistoricalMatch]:
    """
    Find historical incidents similar to a new failure.

    Args:
        equipment_name:      Name of the failing equipment.
        problem_description: Description of the current problem / failure.
        root_cause_hint:     Optional partial root cause if already suspected.
        top_k:               Maximum number of results to return.
        min_similarity:      Minimum cosine similarity (0–1). Default 0.65.

    Returns:
        List of HistoricalMatch, ordered by similarity score descending.
    """
    # Build and embed the query
    parts = [f"Equipment: {equipment_name}", f"Problem: {problem_description}"]
    if root_cause_hint:
        parts.append(f"Root Cause: {root_cause_hint}")
    query_text = ". ".join(parts)

    model = _get_model()
    query_vec = model.encode(query_text, normalize_embeddings=True).astype(np.float32)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD), connection_timeout=3.0)
    try:
        with driver.session() as session:
            # Fetch all incidents with their embeddings, CAPA, and team in one query
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
                           status:         c.status,
                           idx:            c.capa_index
                       }) AS capa_list,
                       collect(DISTINCT p.name) AS team_members
            """)

            incidents = []
            for row in rows:
                node      = dict(row["i"])
                capa_raw  = row["capa_list"]
                team      = [n for n in (row["team_members"] or []) if n]

                # Filter out null CAPA entries (from OPTIONAL MATCH with no match)
                capa = sorted(
                    [c for c in capa_raw if c.get("action")],
                    key=lambda x: (x.get("idx") or 0),
                )
                # Clean up idx from the returned list
                capa_clean = [
                    {k: v for k, v in c.items() if k != "idx"}
                    for c in capa
                ]
                incidents.append((node, capa_clean, team))

        if not incidents:
            return []

        # Compute cosine similarities (vectors are pre-normalized → dot product = cosine)
        emb_matrix = np.array([inc[0]["embedding"] for inc in incidents], dtype=np.float32)
        scores = emb_matrix @ query_vec  # shape: (N,)

        # Rank and filter
        ranked = sorted(
            zip(scores, incidents),
            key=lambda x: x[0],
            reverse=True,
        )

        results = []
        for score, (node, capa, team) in ranked[:top_k]:
            if float(score) < min_similarity:
                break
            results.append(HistoricalMatch(
                source_file       = node.get("source_file", ""),
                plant             = node.get("plant", ""),
                department        = node.get("department", ""),
                equipment         = node.get("equipment", ""),
                occurrence_from   = node.get("occurrence_from"),
                downtime_minutes  = node.get("downtime_minutes"),
                problem_statement = node.get("problem_statement", ""),
                root_cause        = node.get("root_cause", ""),
                capa              = capa,
                team_members      = team,
                similarity_score  = float(score),
            ))

        return results

    finally:
        driver.close()


# ── Prompt formatting (used by Phase 3 LLM integration) ──────────────────────

def format_for_prompt(matches: list[HistoricalMatch]) -> str:
    """
    Format historical matches as a HISTORICAL REFERENCE block to inject into
    the LLM 5 Whys / RCA prompt. Returns an empty string if no matches.
    """
    if not matches:
        return ""

    lines = [
        "━━━ HISTORICAL REFERENCE (Verified plant records) ━━━",
        "Similar incidents found in the knowledge base. Use these as REFERENCE",
        "to guide your analysis — do not assume they are identical to the current case.",
        "",
    ]
    for i, m in enumerate(matches, 1):
        lines.append(f"[Reference {i} — {m.similarity_score:.0%} match]")
        lines.append(f"  Plant / Equipment : {m.plant} — {m.equipment}")
        lines.append(f"  Date              : {m.occurrence_from or 'Unknown'}")
        lines.append(f"  Downtime          : {m.downtime_minutes or '?'} minutes")
        lines.append(f"  Problem           : {m.problem_statement}")
        lines.append(f"  Root Cause Found  : {m.root_cause}")
        if m.capa:
            lines.append("  Actions Taken     :")
            for c in m.capa[:3]:
                owner = f" [{c['responsibility']}]" if c.get("responsibility") else ""
                lines.append(f"    • {c['action']}{owner}")
        if m.team_members:
            lines.append(f"  Investigated by   : {', '.join(m.team_members[:5])}")
        lines.append("")

    lines.append("━━━ END HISTORICAL REFERENCE ━━━")
    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Search historical RCA knowledge graph for similar incidents"
    )
    parser.add_argument("equipment",    help="Equipment name (e.g. 'Coal crusher')")
    parser.add_argument("problem",      help="Problem description")
    parser.add_argument("root_hint",    nargs="?", default="", help="Optional root cause hint")
    parser.add_argument("--top",        type=int,   default=5,    help="Max results (default: 5)")
    parser.add_argument("--threshold",  type=float, default=0.50, help="Min similarity 0–1 (default: 0.50)")
    parser.add_argument("--json",       action="store_true",      help="Output raw JSON instead of formatted text")
    args = parser.parse_args()

    print(f"\nSearching Neo4j at {NEO4J_URI}")
    print(f"  Equipment : {args.equipment}")
    print(f"  Problem   : {args.problem}\n")

    results = find_similar_incidents(
        equipment_name      = args.equipment,
        problem_description = args.problem,
        root_cause_hint     = args.root_hint,
        top_k               = args.top,
        min_similarity      = args.threshold,
    )

    if not results:
        print("No similar incidents found above the similarity threshold.")
        return

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False))
    else:
        print(format_for_prompt(results))
        print(f"\n── Similarity scores ({len(results)} matches) ──")
        for r in results:
            print(f"  [{r.similarity_score:.2%}] {r.source_file:40s}  {r.equipment}")


if __name__ == "__main__":
    _cli()
