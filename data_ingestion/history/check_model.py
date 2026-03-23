"""Quick check if Qwen vision model is available on OpenRouter."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "llm"))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "llm", ".env"))

import requests

key = os.getenv("OPENROUTER_API_KEY", "")
model = os.getenv("VISION_MODEL", "qwen/qwen3.5-9b")

r = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    json={"model": model, "messages": [{"role": "user", "content": "Say hi"}], "max_tokens": 5},
    timeout=30,
)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    print("Model is UP — ready to extract.")
else:
    print(f"Model is DOWN — {r.text[:200]}")
