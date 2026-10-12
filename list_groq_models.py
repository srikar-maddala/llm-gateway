import os

import httpx
from dotenv import load_dotenv

load_dotenv()

resp = httpx.get(
    "https://api.groq.com/openai/v1/models",
    headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
)
print(resp.status_code)
for m in resp.json().get("data", []):
    print(m["id"])