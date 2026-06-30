"""Tests 4-6 — verify ingested data in the self-hosted AWS Weaviate.

Run from the data_ingestion/ folder:  python test_verify.py
(Ingest at least one PDF first, otherwise the count will be 0.)
"""
import logging
from pdf_processor import _load_config, _connect_weaviate

logging.basicConfig(level=logging.WARNING)  # quiet: only show our prints
log = logging.getLogger("test_verify")

cfg = _load_config()
name = cfg["collection"]["name"]
client = _connect_weaviate(cfg, log)
try:
    collection = client.collections.get(name)

    # ── Test 4: total object count ──────────────────────────────────────
    total = collection.aggregate.over_all(total_count=True).total_count
    print(f"\n=== Test 4: total objects in '{name}' ===")
    print("count:", total)

    # ── Test 5: inspect a few stored objects ────────────────────────────
    print("\n=== Test 5: sample stored objects ===")
    for obj in collection.query.fetch_objects(limit=3).objects:
        p = obj.properties
        print({
            "chunkType":  p.get("chunkType"),
            "sourcePdf":  p.get("sourcePdf"),
            "pageNumber": p.get("pageNumber"),
            "chunkIndex": p.get("chunkIndex"),
            "content":    (p.get("content") or "")[:120] + "...",
        })

    # ── Test 6: BM25 retrieval (same path ProdAI uses) ──────────────────
    print("\n=== Test 6: BM25 query 'bearing failure' ===")
    for obj in collection.query.bm25(query="bearing failure", limit=5).objects:
        print("-", (obj.properties.get("content") or "")[:200].replace("\n", " "))
finally:
    client.close()
