import os

from redis import Redis

redis_client = Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    decode_responses=True,
    socket_connect_timeout=0.2,
    socket_timeout=0.2,
)

def get_cache() -> Redis:
    return redis_client