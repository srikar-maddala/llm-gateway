import json
import time

import yaml
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from litellm import acompletion, completion_cost
from pydantic import BaseModel, Field

app = FastAPI()

# Read config.yaml once, when the server starts.
# MODELS maps each alias (fast, smart, local) to its real provider model.
with open("config.yaml") as f:
    CONFIG = yaml.safe_load(f)
MODELS = CONFIG["models"]


class Message(BaseModel):
    role: str
    content: str


class Metadata(BaseModel):
    # Labels about the request. They are NOT sent to the model.
    tenant: str = Field(min_length=1)       # which team or customer is calling
    feature: str = Field(min_length=1)      # which part of their product
    request_id: str = Field(min_length=1)   # unique ID for this one request


class ChatRequest(BaseModel):
    model: str
    messages: list[Message]
    metadata: Metadata


@app.get("/health")
def health():
    return {"status": "ok"}


# /v1 = version 1 of the API; /chat/completions = "generate the next reply".
# POST because the client sends a body (the messages) for us to process.
@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    # 1. Look up the alias. Unknown alias -> 400 (the client's mistake).
    cfg = MODELS.get(req.model)
    if cfg is None:
        raise HTTPException(status_code=400, detail=f"Unknown model '{req.model}'. Available: {list(MODELS)}")

    # 2. Convert Pydantic Message objects into plain dicts for LiteLLM.
    messages = [m.model_dump() for m in req.messages]

    # 3. Start the record with what we know before calling the model.
    record = {
        "request_id": req.metadata.request_id,
        "tenant": req.metadata.tenant,
        "feature": req.metadata.feature,
        "model": req.model,
        "provider": cfg["provider"],
    }

    # 4. Call the provider, timing it. If the provider fails, log it and return 502.
    start = time.perf_counter()
    try:
        response = await acompletion(
            model=cfg["litellm_model"],
            messages=messages,
            api_base=cfg.get("api_base"),
        )
    except Exception as exc:
        record["status"] = "error"
        record["error_type"] = type(exc).__name__
        record["latency_ms"] = round((time.perf_counter() - start) * 1000)
        print(json.dumps(record))
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}")

    # 5. Success: add latency, tokens, and cost to the record.
    record["status"] = "ok"
    record["latency_ms"] = round((time.perf_counter() - start) * 1000)
    record["input_tokens"] = response.usage.prompt_tokens
    record["output_tokens"] = response.usage.completion_tokens
    try:
        record["cost_usd"] = round(completion_cost(completion_response=response), 6)
    except Exception:
        record["cost_usd"] = None  # LiteLLM has no price for this model

    # 6. One JSON line per request in the server terminal.
    print(json.dumps(record))
    return response