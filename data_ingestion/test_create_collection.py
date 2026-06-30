"""Test 2 — create the 'rca' collection only (schema, no data ingested).

Run from the data_ingestion/ folder:  python test_create_collection.py
Expected: logs 'Created collection 'rca' (BM25-only, no vectorizer)' then
'Collection ready: rca'. Re-running is safe (it reuses an existing collection).
"""
import logging
from pdf_processor import _load_config, _connect_weaviate, _create_collection

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("test_create_collection")

cfg = _load_config()
client = _connect_weaviate(cfg, log)
try:
    _create_collection(client, cfg, log)
    print("Collection ready:", cfg["collection"]["name"])
finally:
    client.close()
