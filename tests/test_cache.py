import json
from datetime import datetime, timedelta, timezone

from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.orm import Session


def create_short_url(client):
    response = client.post(
        "/api/v1/urls",
        json={"long_url": "https://example.com/articles/123"},
    )
    assert response.status_code == 201
    return response.json()["code"]


def test_redirect_cache_hit(client, cache, monkeypatch):
    code = create_short_url(client)
    cache_key = f"url:{code}"

    # First request: cache miss -> PostgreSQL -> Redis
    response = client.get(f"/{code}", follow_redirects=False)

    assert response.status_code == 302
    assert cache.exists(cache_key) == 1

    cached_data = json.loads(cache.get(cache_key))
    assert cached_data["original_url"] == "https://example.com/articles/123"

    # Fail the test if the second request queries PostgreSQL.
    def fail_db_query(*args, **kwargs):
        raise AssertionError("Database was queried on cache hit")

    monkeypatch.setattr(Session, "scalar", fail_db_query)

    # Second request: must use Redis
    response = client.get(f"/{code}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/articles/123"


def test_redirect_redis_unavailable(client, cache, monkeypatch):
    code = create_short_url(client)

    # Simulate Redis connection failure
    def redis_unavailable(*args, **kwargs):
        raise RedisConnectionError("Redis is unavailable")

    monkeypatch.setattr(cache, "get", redis_unavailable)
    monkeypatch.setattr(cache, "set", redis_unavailable)

    # Should fall back to PostgreSQL
    response = client.get(f"/{code}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/articles/123"


def test_redirect_expired_cache(client, cache):
    code = "expired1"
    cache_key = f"url:{code}"

    expired_at = datetime.now(timezone.utc) - timedelta(seconds=10)

    # Manually populate Redis with an already-expired URL
    cache.set(
        cache_key,
        json.dumps({
            "original_url": "https://example.com",
            "expires_at": expired_at.isoformat(),
        }),
        ex=3600,
    )

    response = client.get(f"/{code}", follow_redirects=False)

    assert response.status_code == 410
    assert response.json()["detail"] == "URL has expired"


def test_cache_ttl_respects_expiration(client, cache):
    response = client.post(
        "/api/v1/urls",
        json={
            "long_url": "https://example.com/articles/123",
            "expires_in_seconds": 60,
        },
    )

    assert response.status_code == 201
    code = response.json()["code"]

    response = client.get(
        f"/{code}",
        follow_redirects=False,
    )

    assert response.status_code == 302

    ttl = cache.ttl(f"url:{code}")

    assert 0 < ttl <= 60