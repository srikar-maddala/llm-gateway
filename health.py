"""Track each provider's recent health and latency in Redis."""

import time

import redis.asyncio as redis

from errors import PROVIDER_FAULTS

r = redis.Redis(host="localhost", port=6379, decode_responses=True,
                socket_connect_timeout=0.5 ,#give up connecting after 0.5 s
                socket_timeout=0.5,) #give up waiting for a reply after 0.5s

# Settings
BUCKET_SECONDS = 60    # one counter per minute (one "page")
WINDOW_MINUTES = 5     # health looks at the last 5 pages
LATENCY_SAMPLES = 100  # keep the last 100 latencies per provider
REDIS_RETRY_AFTER = 30.0   # after a Redis failure, skip it for this many seconds
_redis_down_until = 0.0     # time until which we skip Redis

def _redis_available() -> bool:
    """False while we're waiting after a recent Redis failure."""
    return time.monotonic() >= _redis_down_until

def _mark_redis_down(exc: Exception) -> None:
    """Remember that Redis failed, so we skip it for a while."""
    global _redis_down_until
    _redis_down_until = time.monotonic() + REDIS_RETRY_AFTER
    print(f"WARNING: Redis unavailable, skipping it for {REDIS_RETRY_AFTER:.0f}s: {exc}")


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
    try:
        await r.incr(key)
        await r.expire(key,WINDOW_MINUTES*60)
    except (redis.RedisError,OSError) as exc:
        print(f"WARNING:health tracking unavailable: {exc}")    
    


async def record_latency(provider: str, latency_ms: int) -> None:
    """Remember this request's latency; keep only the most recent ones."""
    if not _redis_available():
        return  # Redis failed recently; don't slow this request down
    key = f"latency:{provider}"
    try:
        await r.lpush(key, latency_ms)               # add to the front of the list
        await r.ltrim(key, 0, LATENCY_SAMPLES - 1)   # cut the list to 100 items
    except (redis.RedisError,OSError) as exc:
        _mark_redis_down(exc)

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