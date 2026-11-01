import json
import logging

from app.logging_config import JSONFormatter
from redis.exceptions import ConnectionError as RedisConnectionError


def test_json_formatter():
    logger = logging.getLogger("app.test")

    record = logger.makeRecord(
        name="app.test",
        level=logging.INFO,
        fn=__file__,
        lno=10,
        msg="Test log message",
        args=(),
        exc_info=None,
        extra={"event": "test_event"},
    )

    formatter = JSONFormatter()
    output = formatter.format(record)

    data = json.loads(output)

    assert data["level"] == "INFO"
    assert data["logger"] == "app.test"
    assert data["message"] == "Test log message"
    assert data["event"] == "test_event"
    assert "timestamp" in data


def test_http_request_logging(client, caplog):
    request_logger = logging.getLogger("app.http")

    # Our app logger has propagate=False, so attach
    # pytest's capture handler directly.
    request_logger.addHandler(caplog.handler)

    try:
        response = client.get("/health")
    finally:
        request_logger.removeHandler(caplog.handler)

    assert response.status_code == 200

    records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "http_request"
    ]

    assert len(records) == 1

    record = records[0]

    assert record.method == "GET"
    assert record.path == "/health"
    assert record.status_code == 200
    assert record.duration_ms >= 0


def test_redis_cache_hit_and_miss_logging(client, caplog):
    logger = logging.getLogger("app.services.redirect_service")
    logger.addHandler(caplog.handler)

    try:
        response = client.post(
            "api/v1/urls",
            json={"long_url": "https://example.com"},
        )
        assert response.status_code == 201

        code = response.json()["code"]

        # First redirect: cache miss
        caplog.clear()

        first = client.get(
            f"/{code}",
            follow_redirects=False,
        )

        first_events = [
            record.event
            for record in caplog.records
            if record.name == logger.name
            and hasattr(record, "event")
        ]

        # Second redirect: cache hit
        caplog.clear()

        second = client.get(
            f"/{code}",
            follow_redirects=False,
        )

        second_events = [
            record.event
            for record in caplog.records
            if record.name == logger.name
            and hasattr(record, "event")
        ]

    finally:
        logger.removeHandler(caplog.handler)

    assert first.status_code == 302
    assert second.status_code == 302

    assert first_events == ["redis_cache_miss"]
    assert second_events == ["redis_cache_hit"]


def test_redis_unavailable_logging(
    client, cache, caplog, monkeypatch
):
    # Create a short URL while Redis is available
    response = client.post(
        "/api/v1/urls",
        json={"long_url": "https://example.com"}
    )
    assert response.status_code == 201
    code = response.json()["code"]

    # Simulate a Redis connection failure
    def redis_unavailable(*arg, **kwargs):
        raise RedisConnectionError("Redis unavailable")

    monkeypatch.setattr(cache, "get", redis_unavailable)

    logger = logging.getLogger("app.services.redirect_service")
    logger.addHandler(caplog.handler)

    try:
        response = client.get(
            f"/{code}",
            follow_redirects=False,
        )
    finally:
        logger.removeHandler(caplog.handler)

    # PostgreSQL fallback should still work
    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/"

    records = [
        record
        for record in caplog.records
        if record.name == logger.name
    ]

    events = [
        getattr(record, "event", None)
        for record in caplog.records
    ]

    assert "redis_cache_unavailable" in events
    assert "redis_cache_miss" not in events

    warning_records = [
        record
        for record in records
        if getattr(record, "event", None)
        == "redis_cache_unavailable"
    ]

    assert warning_records[0].levelname == "WARNING"




