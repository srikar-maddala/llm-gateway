import json
import time
import os
import yaml
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response                            # NEW
from litellm import acompletion, completion_cost
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest  # NEW
from pydantic import BaseModel, Field

from breaker import is_open, maybe_trip
from errors import PROVIDER_FAULTS, classify_error
from health import get_health, record_latency, record_result
from metrics import CIRCUIT_OPEN, COST, LATENCY, PROVIDER_ATTEMPTS, REQUESTS  # NEW

app = FastAPI()

# Read config.yaml once, when the server starts.
# MODELS maps each alias (fast, smart, local) to its real provider model and fallbacks.
with open("config.yaml") as f:
    CONFIG = yaml.safe_load(f)
MODELS = CONFIG["models"]

# Inside Docker, Ollama on your PC is reached at host.docker.internal, not localhost.
OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE")
if OLLAMA_API_BASE:
    for model_cfg in MODELS.values():
        if model_cfg["provider"] == "ollama":
            model_cfg["api_base"] = OLLAMA_API_BASE
            
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
        provider = step_cfg["provider"]

        # Circuit breaker: skip providers that are currently known to be broken
        if await is_open(provider):
            attempts.append({
                "model": alias,
                "provider": provider,
                "error_category": "circuit_open",
                "latency_ms": 0,
            })
            PROVIDER_ATTEMPTS.labels(provider=provider, outcome="circuit_open").inc()  # NEW
            continue

        start = time.perf_counter()
        try:
            response = await acompletion(
                model=step_cfg["litellm_model"],
                messages=messages,
                api_base=step_cfg.get("api_base"),
            )
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start) * 1000)
            category = classify_error(exc)                              # what kind of error?
            PROVIDER_ATTEMPTS.labels(provider=provider, outcome=category).inc()  # NEW
            await record_result(provider, ok=False, category=category)  # count it
            if category in PROVIDER_FAULTS:                             # maybe open the breaker
                await maybe_trip(provider)
            attempts.append({                                           # note it in the log
                "model": alias,
                "provider": provider,
                "error_category": category,
                "latency_ms": latency_ms,
            })
            if category == "bad_request":                               # client's fault: stop
                break
            continue                                                    # try the next provider

        # 5. Success: record it and return the answer.
        latency_ms = round((time.perf_counter() - start) * 1000)
        await record_result(provider, ok=True)
        await record_latency(provider, latency_ms)

        record["status"] = "ok"
        record["served_by"] = alias
        record["provider"] = provider
        record["latency_ms"] = latency_ms
        record["attempts"] = attempts
        record["input_tokens"] = response.usage.prompt_tokens
        record["output_tokens"] = response.usage.completion_tokens
        try:
            record["cost_usd"] = round(completion_cost(completion_response=response), 6)
        except Exception:
            record["cost_usd"] = None  # LiteLLM has no price for this model
        print(json.dumps(record))

        # NEW: update Prometheus metrics for this successful request
        PROVIDER_ATTEMPTS.labels(provider=provider, outcome="ok").inc()
        LATENCY.labels(provider=provider).observe(latency_ms / 1000)   # seconds
        REQUESTS.labels(model=req.model, served_by=alias, status="ok").inc()
        if record["cost_usd"]:                                         # skip None and 0.0
            COST.labels(
                tenant=req.metadata.tenant,
                feature=req.metadata.feature,
                provider=provider,
            ).inc(record["cost_usd"])

        # Return the normal response PLUS a "gateway" section,
        # so the caller can see who actually answered and what failed first.
        body = response.model_dump()
        body["gateway"] = {
            "served_by": alias,
            "provider": provider,
            "latency_ms": latency_ms,
            "attempts": attempts,
        }
        return body

    # 6. Every alias in the chain failed.
    record["status"] = "error"
    record["attempts"] = attempts
    print(json.dumps(record))
    REQUESTS.labels(model=req.model, served_by="none", status="error").inc()  # NEW
    raise HTTPException(status_code=502, detail={"message": "All providers failed", "attempts": attempts})


@app.get("/providers/health")
async def providers_health():
    providers = sorted({cfg["provider"] for cfg in MODELS.values()})
    result = []
    for p in providers:
        h = await get_health(p)
        h["circuit"] = "open" if await is_open(p) else "closed"
        result.append(h)
    return result


# NEW: the page Prometheus reads every few seconds
@app.get("/metrics")
async def metrics():
    # Refresh breaker state right before Prometheus reads it.
    for p in sorted({cfg["provider"] for cfg in MODELS.values()}):
        CIRCUIT_OPEN.labels(provider=p).set(1 if await is_open(p) else 0)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)