"""Track each provider's recent successes and failures in Redis."""
import time
import redis.asyncio as redis
from errors import PROVIDER_FAULTS

r=redis.Redis(host='localhost',port=6379,decode_responses=True)

BUCKET_SECONDS=60 # one counter per minute(one "page")
WINDOW_MINUTES=5  #health looks at the last 5 pages

def _current_bucket()-> int:
    return int(time.time() // BUCKET_SECONDS)

async def record_result(provider:str,ok:bool,category:str | None=None) -> None:
    """Count one request's outcome for this provider"""
    if ok:
        outcome="success"
    elif category in PROVIDER_FAULTS:
        outcome='failure'
    else:
        return # not the provider's fault, so dont count it

    key=f"health:{provider}:{outcome}:{_current_bucket()}"
    await r.incr(key)
    await r.expire(key,WINDOW_MINUTES*60)

async def get_health(provider:str) ->dict:
    """ Add up last few minutes of counters for the provider"""
    now=_current_bucket()
    successes=failures=0
    for bucket in range(now-WINDOW_MINUTES+1,now+1):
        successes+=int(await r.get(f"health:{provider}:success:{bucket}")or 0)
        failures+= int(await r.get(f"health:{provider}:failure:{bucket}")or 0)

    total=successes+failures
    return{
        "provider":provider,
        "successes":successes,
        'failures':failures,
        'error_rate':round(failures / total, 3) if total else 0.0,
    }    

        