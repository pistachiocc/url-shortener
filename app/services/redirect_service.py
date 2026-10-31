import json
from datetime import datetime, timezone

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import URL


MAX_CACHE_TTL = 3600


class URLNotFoundError(Exception):
    pass


class URLExpiredError(Exception):
    pass


def get_original_url(
    code: str,
    db: Session,
    cache: Redis,
) -> str:
    cache_key = f"url:{code}"

    # 1. Try Redis first
    try:
        cached = cache.get(cache_key)
    except RedisError:
        cached = None

    if  cached is not None:
        try:
            data = json.loads(cached)

            if not isinstance(data, dict):
                raise ValueError("Invalid cache entry")

            original_url = data["original_url"]

            if not isinstance(original_url, str) or not original_url.startswith(("http://", "https://")):
                raise ValueError("Invalid cached URL")

            expires_at = (
                datetime.fromisoformat(data["expires_at"])
                if data["expires_at"] is not None
                else None
            )

            if expires_at is not None and expires_at <= datetime.now(timezone.utc):
                raise URLExpiredError("URL has expired")

            return original_url
        
        except (ValueError, TypeError, KeyError):
            # Invalid cache entry: fall back to database
            pass

    # 2. Query PostgreSQL on cache miss or Redis failure
    url = db.scalar(
        select(URL).where(URL.short_code == code)
    )

    if url is None:
        raise URLNotFoundError("URL not found")

    if url.expires_at is not None and url.expires_at <= datetime.now(timezone.utc):
        raise URLExpiredError("URL has expired")

    # 3. Calculate cache TTL
    cache_ttl = MAX_CACHE_TTL

    if url.expires_at is not None:
        remaining = (url.expires_at - datetime.now(timezone.utc)).total_seconds()
        cache_ttl = min(cache_ttl, int(remaining))

    # 4. Populate Redis
    if cache_ttl > 0:
        data = {
            "original_url": url.original_url,
            "expires_at": (
                url.expires_at.isoformat()
                if url.expires_at is not None
                else None
            ),
        }

        try:
            cache.set(
                cache_key,
                json.dumps(data),
                ex=cache_ttl,
            )
        except RedisError:
            pass

    return url.original_url
    