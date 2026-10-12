from dotenv import load_dotenv
load_dotenv()
#reads .env so LiteLLM can find OPEN_API_KEY and GROQ_API_KEY
from litellm import completion
messages = [{"role": "user", "content": "In one sentence, what is a circuit breaker in software?"}]

#1.Ollama (Local,free,no key)
response = completion(
    model="ollama/llama3.2",
    messages=messages,
    api_base="http://localhost:11434",
)
print('OLLAMA:',response.choices[0].message.content)
#Basically there are different choices in the responses we are going to select first one also
#In message the model sent back which has role and content we are going to access content
print(response.usage)
#Usage is nothing but gives information about prompt_tokens , completion_tokens, toatl_tokens addition of both

print()

# 2. OpenAI (uses OPENAI_API_KEY from .env)
response = completion(
    model="openai/gpt-4o-mini",
    messages=messages,
)
print("OPENAI:", response.choices[0].message.content)
print(response.usage)
print()

# 3. Groq (uses GROQ_API_KEY from .env)
response = completion(
    model="groq/openai/gpt-oss-20b",
    messages=messages,
)
print("GROQ:", response.choices[0].message.content)
print(response.usage)

#The model has two parts : provider/model part before the slash tells LiteLLM which provider to call 
#Only the model changes between calls: The messages and the response shape are identical, which is exactly the point of LiteLLM and the reason your gateway can swap providers during failover.
