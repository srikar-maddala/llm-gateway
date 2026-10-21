"""Chaos test: send many requests to one alias and measure what users experience.

Usage:  python chaos_test.py <scenario-name> [number-of-requests]
Example: python chaos_test.py groq-down 20
"""

import sys
import time
import uuid

import httpx

GATEWAY = "http://localhost:8000"
MODEL = "fast"
PROMPT = "In one sentence, what is a circuit breaker in software?"

def percentile(values: list[int], p: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round(p / 100 * (len(ordered) - 1))
    return ordered[index]

def main() -> None:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "unnamed"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    ok = 0
    latencies = []
    served = {}  # who answered -> how many times

    with httpx.Client(timeout=120) as client:
        for i in range(n):
            start = time.perf_counter()
            resp = client.post(
                f"{GATEWAY}/v1/chat/completions",
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": PROMPT}],
                    "metadata": {
                        "tenant": "demo-team",
                        "feature": f"chaos-{scenario}",
                        "request_id": str(uuid.uuid4()),
                    },
                },
            )
            ms = round((time.perf_counter() - start) * 1000)
            latencies.append(ms)

            if resp.status_code == 200:
                ok += 1
                body = resp.json()
                who = body.get("gateway", {}).get("served_by") or body.get("served_by") or "?"
            else:
                who = f"HTTP {resp.status_code}"
            served[who] = served.get(who, 0) + 1
            print(f"{i + 1:>3}  {who:<10} {ms} ms")

    print()
    print(f"Scenario:      {scenario}")
    print(f"Requests:      {n}")
    print(f"Success rate:  {ok}/{n} = {ok / n:.0%}")
    print(f"Served by:     {served}")
    print(f"Latency p50:   {percentile(latencies, 50)} ms")
    print(f"Latency p95:   {percentile(latencies, 95)} ms")
    print(f"Latency max:   {max(latencies)} ms")


if __name__ == "__main__":
    main()