"""Track each provider's recent health and latency in Redis."""

import time

import redis.asyncio as redis

from errors import PROVIDER_FAULTS

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

# Settings
BUCKET_SECONDS = 60    # one counter per minute (one "page")
WINDOW_MINUTES = 5     # health looks at the last 5 pages
LATENCY_SAMPLES = 100  # keep the last 100 latencies per provider


def _current_bucket() -> int:
    """Which minute (page) are we in right now?"""
    return int(time.time() // BUCKET_SECONDS)


def _percentile(values: list[int], p: float) -> int | None:
    """Return the p-th percentile (0-100) of a list of numbers."""
    if not values:
        return None
    ordered = sorted(values)
    index = round(p / 100 * (len(ordered) - 1))
    return ordered[index]


async def record_result(provider: str, ok: bool, category: str | None = None) -> None:
    """Count one request's outcome for this provider."""
    if ok:
        outcome = "success"
    elif category in PROVIDER_FAULTS:
        outcome = "failure"
    else:
        return  # not the provider's fault, so don't count it

    key = f"health:{provider}:{outcome}:{_current_bucket()}"
    await r.incr(key)
    await r.expire(key, WINDOW_MINUTES * 60)


async def record_latency(provider: str, latency_ms: int) -> None:
    """Remember this request's latency; keep only the most recent ones."""
    key = f"latency:{provider}"
    await r.lpush(key, latency_ms)               # add to the front of the list
    await r.ltrim(key, 0, LATENCY_SAMPLES - 1)   # cut the list to 100 items


async def get_health(provider: str) -> dict:
    """Summarise this provider's recent successes, failures, and latency."""
    # Successes and failures over the last WINDOW_MINUTES
    now = _current_bucket()
    successes = failures = 0
    for bucket in range(now - WINDOW_MINUTES + 1, now + 1):
        successes += int(await r.get(f"health:{provider}:success:{bucket}") or 0)
        failures += int(await r.get(f"health:{provider}:failure:{bucket}") or 0)
    total = successes + failures

    # Latency percentiles over the last LATENCY_SAMPLES successful requests
    raw = await r.lrange(f"latency:{provider}", 0, -1)
    latencies = [int(x) for x in raw]

    return {
        "provider": provider,
        "successes": successes,
        "failures": failures,
        "error_rate": round(failures / total, 3) if total else 0.0,
        "p50_latency_ms": _percentile(latencies, 50),
        "p95_latency_ms": _percentile(latencies, 95),
    }