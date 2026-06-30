"""Test 1 — verify Python can connect to the self-hosted AWS Weaviate.

Uses the same _load_config() + _connect_weaviate() the real pipeline uses,
so this also validates that .env (URL, API key, gRPC settings) is correct.

Run from the data_ingestion/ folder:  python test_connection.py
Expected output:  is_ready: True
"""
import logging
from pdf_processor import _load_config, _connect_weaviate

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("test_connection")

cfg = _load_config()
client = _connect_weaviate(cfg, log)
try:
    print("is_ready:", client.is_ready())
finally:
    client.close()
