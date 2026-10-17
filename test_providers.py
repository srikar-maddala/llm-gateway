"""Send the same prompt to every model alias through the gateway and compare them.

Start the gateway first (uvicorn main:app --reload), then run:
    python test_providers.py
"""

import time
import uuid

import httpx

GATEWAY = "http://127.0.0.1:8000"
PROMPT = "In one sentence, what is a circuit breaker in software?"
ALIASES = ["fast", "smart", "local"]


def main():
    print(f"{'alias':<8}{'status':<8}{'latency_ms':<12}{'in_tokens':<11}{'out_tokens':<11}answer")
    print("-" * 90)

    for alias in ALIASES:
        body = {
            "model": alias,
            "messages": [{"role": "user", "content": PROMPT}],
            "metadata": {
                "tenant": "demo-team",
                "feature": "provider-test",
                "request_id": str(uuid.uuid4()),  # a fresh unique ID for every request
            },
        }

        start = time.perf_counter()
        resp = httpx.post(f"{GATEWAY}/v1/chat/completions", json=body, timeout=60)
        latency_ms = round((time.perf_counter() - start) * 1000)

        if resp.status_code != 200:
            try:
                detail = resp.json().get("detail", "")
            except ValueError:
                detail = resp.text  # not JSON, e.g. a plain "Internal Server Error"
            print(f"{alias:<8}{resp.status_code:<8}{latency_ms:<12}{'-':<11}{'-':<11}{str(detail)[:50]}")
            continue

        data = resp.json()
        usage = data["usage"]
        answer = data["choices"][0]["message"]["content"].replace("\n", " ")[:50]
        print(f"{alias:<8}{'ok':<8}{latency_ms:<12}{usage['prompt_tokens']:<11}{usage['completion_tokens']:<11}{answer}")


if __name__ == "__main__":
    main()      