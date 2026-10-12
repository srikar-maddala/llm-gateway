from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI
from litellm import acompletion
from pydantic import BaseModel

app=FastAPI()
class Message(BaseModel):
    role:str
    content:str
class ChatRequest(BaseModel):
    model:str
    messages:list[Message]   
@app.get("/health")
def health():
    return {"status": "ok"}

#
@app.post('/v1/chat/completions')
#/v1 means version 1 of the API 
#/chat/completions means 'complete this chat' , that is generate the next reply
#Why Post
#/health only reads a status, so it uses GET. 
# This endpoint receives data (the messages) and processes it into a reply, 
# and that data travels in the request body. Request bodies go with POST, not GET.
@app.post('/v1/chat/completions')
async def chat_completions(req:ChatRequest):
    messages=[m.model_dump() for m in req.messages]
    # messages = []
    # for m in req.messages:
    #     messages.append(m.model_dump())
    #messages.append(m.model_dump()) converts m into a dictionary with .model_dump() and adds it to the list.
    api_base = "http://localhost:11434" if req.model.startswith("ollama/") else None
    response = await acompletion(model=req.model, messages=messages, api_base=api_base)
    return response
