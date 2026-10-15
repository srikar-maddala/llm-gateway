from dotenv import load_dotenv
import yaml
import json
import time
from fastapi import FastAPI, HTTPException
load_dotenv()
from litellm import acompletion, completion_cost
from pydantic import BaseModel,Field

app=FastAPI()
with open("config.yaml") as f:
    CONFIG = yaml.safe_load(f)
MODELS = CONFIG["models"]
class Message(BaseModel):
    role:str
    content:str

class Metadata(BaseModel):
    tenant: str = Field(min_length=1)
    feature: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
class ChatRequest(BaseModel):
    model:str
    messages:list[Message]   
    metadata:Metadata
@app.get("/health")
def health():
    return {"status": "ok"}


#/v1 means version 1 of the API 
#/chat/completions means 'complete this chat' , that is generate the next reply
#Why Post
#/health only reads a status, so it uses GET. 
# This endpoint receives data (the messages) and processes it into a reply, 
# and that data travels in the request body. Request bodies go with POST, not GET.
@app.post('/v1/chat/completions')
async def chat_completions(req: ChatRequest):
    cfg = MODELS.get(req.model)
    if cfg is None:
        raise HTTPException(status_code=400, detail=f"Unknown model '{req.model}'. Available: {list(MODELS)}")
    messages = [m.model_dump() for m in req.messages]

    # Labels we know before calling the model
    record = {
        "request_id": req.metadata.request_id,
        "tenant": req.metadata.tenant,
        "feature": req.metadata.feature,
        "model": req.model,
        "provider": cfg["provider"],
    }

    start = time.perf_counter()
    response = await acompletion(model=cfg['litellm_model'], messages=messages, api_base=cfg.get("api_base"))

    # What we learned from the call
    record["latency_ms"] = round((time.perf_counter() - start) * 1000)
    record["input_tokens"] = response.usage.prompt_tokens
    record["output_tokens"] = response.usage.completion_tokens
    try:
        record["cost_usd"] = round(completion_cost(completion_response=response), 6)
    except Exception:
        record["cost_usd"] = None  # LiteLLM has no price for this model

    # One line per request
    print(json.dumps(record))
    return response
