import json
import time

import yaml
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from litellm import acompletion, completion_cost
from pydantic import BaseModel, Field

from errors import classify_error
from health import get_health, record_latency, record_result

app = FastAPI()

# Read config.yaml once, when the server starts.
# MODELS maps each alias (fast, smart, local) to its real provider model and fallbacks.
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
    }

    # 4. Try the requested alias first, then its fallbacks, in order.
    chain = [req.model] + cfg.get("fallbacks", [])
    attempts = []  # what happened at each failed step

    for alias in chain:
        step_cfg = MODELS[alias]
        start = time.perf_counter()
        try:
            response = await acompletion(
                model=step_cfg["litellm_model"],
                messages=messages,
                api_base=step_cfg.get("api_base"),
            )
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start) * 1000)
            category = classify_error(exc)
            await record_result(step_cfg["provider"], ok=False, category=category)
            attempts.append({
                "model": alias,
                "provider": step_cfg["provider"],
                "error_category": category,
                "latency_ms": latency_ms,
            })
            if category == "bad_request":
                break      # the client's request is invalid; another provider won't help
            continue       # try the next alias in the chain

        # 5. Success: record it and return the answer.
        latency_ms = round((time.perf_counter() - start) * 1000)
        await record_result(step_cfg["provider"], ok=True)
        await record_latency(step_cfg["provider"], latency_ms)

        record["status"] = "ok"
        record["served_by"] = alias
        record["provider"] = step_cfg["provider"]
        record["latency_ms"] = latency_ms
        record["attempts"] = attempts
        record["input_tokens"] = response.usage.prompt_tokens
        record["output_tokens"] = response.usage.completion_tokens
        try:
            record["cost_usd"] = round(completion_cost(completion_response=response), 6)
        except Exception:
            record["cost_usd"] = None  # LiteLLM has no price for this model
        print(json.dumps(record))
        return response

    # 6. Every alias in the chain failed.
    record["status"] = "error"
    record["attempts"] = attempts
    print(json.dumps(record))
    raise HTTPException(status_code=502, detail={"message": "All providers failed", "attempts": attempts})


@app.get("/providers/health")
async def providers_health():
    providers = sorted({cfg["provider"] for cfg in MODELS.values()})
    return [await get_health(p) for p in providers]