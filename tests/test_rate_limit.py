from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import func, select

from app import rate_limit
from app.main import app
from app.models import URL

def create_url(client):
    return client.post(
        "/api/v1/urls",
        json={"long_url": "https://example.com"}
    )

def test_rate_limit_exceeded(client, monkeypatch):
    # Freeze time within one fixed window
    monkeypatch.setattr(
        rate_limit,
        "current_time_seconds",
        lambda: 120,
    )

    # First 10 requests are allowed
    for _ in range(10):
        response = create_url(client)
        assert response.status_code == 201

    # 11th request is rejected
    response = create_url(client)

    assert response.status_code == 429
    assert response.json()["detail"] == "Rate limit exceeded"
    assert response.headers["retry-after"] == "60"


def test_rate_limit_window_reset(client, monkeypatch):
    monkeypatch.setattr(
        rate_limit,
        "current_time_seconds",
        lambda: 120,
    )

    for _ in range(10):
        assert create_url(client).status_code == 201

    assert create_url(client).status_code == 429

    # Move to the next one-minute window
    monkeypatch.setattr(
        rate_limit,
        "current_time_seconds",
        lambda: 180,
    )

    assert create_url(client).status_code == 201


def test_rate_limit_per_ip(client, monkeypatch):
    monkeypatch.setattr(
        rate_limit,
        "current_time_seconds",
        lambda: 120,
    )

    # Reuse dependency overrides from the client fixture
    with (
        TestClient(
            app,
            client=("198.51.100.1", 50000),
        ) as client_a,
        TestClient(
            app,
            client=("198.51.100.2", 50000),
        ) as client_b,
    ): 
        for _ in range(10):
            assert create_url(client_a).status_code == 201

        assert create_url(client_a).status_code == 429

        # A different IP has its own counter
        assert create_url(client_b).status_code == 201


def test_rate_limit_redis_unavailable(client, cache, monkeypatch):
    def redis_unavailable(*arg, **kwargs):
        raise RedisConnectionError("Redis unavailable")

    monkeypatch.setattr(
        cache,
        "pipeline",
        redis_unavailable,
    )

    # Fall-open: requests are allowed when Redis is unavailable
    response = create_url(client)

    assert response.status_code == 201


def test_rate_limit_does_not_write_to_db(
    client, db_connection, monkeypatch
):
    monkeypatch.setattr(
        rate_limit,
        "current_time_seconds",
        lambda: 120,
    )

    count_query = select(func.count()).select_from(URL)

    before = db_connection.execute(count_query).scalar_one()

    for _ in range(10):
        assert create_url(client).status_code == 201

    response = create_url(client)

    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"

    after = db_connection.execute(count_query).scalar_one()

    assert after - before == 10