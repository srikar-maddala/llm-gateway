"""Circuit breaker: stop sending traffic to a provider that is clearly failing."""
import redis.asyncio as redis
from health import get_health, r

MIN_REQUESTS = 3            # need at least this many recent requests to judge
ERROR_RATE_THRESHOLD = 0.5  # trip when half or more of them failed
COOLDOWN_SECONDS = 30       # how long to skip the provider once tripped


async def is_open(provider: str) -> bool:
    """True if the breaker is open, meaning skip this provider for now."""
    try:
        return await r.exists(f"breaker:{provider}") == 1
    except (redis.RedisError, OSError):
        return False  # if Redis is down, don't block any traffic


async def maybe_trip(provider: str) -> None:
    """After a provider fault, open the breaker if the provider looks broken."""
    try:
        health = await get_health(provider)
        total = health["successes"] + health["failures"]
        if total >= MIN_REQUESTS and health["error_rate"] >= ERROR_RATE_THRESHOLD:
            await r.set(f"breaker:{provider}", "open", ex=COOLDOWN_SECONDS)
            print(f"WARNING: circuit OPEN for {provider} for {COOLDOWN_SECONDS}s "
                  f"(error rate {health['error_rate']:.0%} over {total} requests)")
    except (redis.RedisError, OSError):
        pass  # can't judge without Redis; leave the breaker closed