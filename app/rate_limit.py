import logging
import time

from fastapi import Depends, HTTPException, Request
from redis import Redis
from redis.exceptions import RedisError

from .cache import get_cache

logger = logging.getLogger(__name__)

RATE_LIMIT = 10
WINDOW_SECONDS = 60


def current_time_seconds() -> int:
    return int(time.time())

def enforce_create_rate_limit(
    request: Request,
    cache: Redis = Depends(get_cache),
) -> None:
    client_ip = (
        request.client.host
        if request.client is not None
        else "unknown"
    )

    now = current_time_seconds()
    window = now // WINDOW_SECONDS

    key = f"rate_limit:create_url:{client_ip}:{window}"

    try:
        with cache.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, WINDOW_SECONDS, nx=True)
            results = pipe.execute()

        count = results[0]

    except RedisError:
        logger.warning(
            "Redis rate limiter unavailable; allowing request",
            exc_info=True,
        )
        return

    if count > RATE_LIMIT:
        retry_after = WINDOW_SECONDS - (now % WINDOW_SECONDS)

        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )