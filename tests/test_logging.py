import json
import logging
import asyncio
import httpx

from uuid import UUID
from io import StringIO

from app.logging_config import JSONFormatter
from app.main import app
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


def test_request_id_header_is_unique(client):
    first = client.get("/health")
    second = client.get("/health")

    assert first.status_code == 200
    assert second.status_code == 200

    first_id = first.headers["X-Request-ID"]
    second_id = second.headers["X-Request-ID"]

    assert UUID(first_id).version == 4
    assert UUID(second_id).version == 4

    assert first_id != second_id


def test_request_id_header_on_http_error(client):
    response = client.get("/missing0")

    assert response.status_code == 404

    request_id = response.headers["X-Request-ID"]

    assert UUID(request_id).version == 4


def test_request_id_correlates_http_and_cache_logs(client):
    # Create a short URL
    response = client.post(
        "/api/v1/urls",
        json={"long_url": "https://example.com"},
    )
    assert response.status_code == 201
    code = response.json()["code"]

    # Capture formatted JSON logs from all app loggers
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JSONFormatter())

    app_logger = logging.getLogger("app")
    app_logger.addHandler(handler)

    try:
        # First request: cache miss
        first = client.get(
            f"/{code}",
            follow_redirects=False
        )

        # Second request: cache hit
        second = client.get(
            f"/{code}",
            follow_redirects=False
        )
    finally:
        app_logger.removeHandler(handler)
        handler.close()

    assert first.status_code == 302
    assert second.status_code == 302

    first_id = first.headers["X-Request-ID"]
    second_id = second.headers["X-Request-ID"]

    assert first_id != second_id

    logs = [
        json.loads(line)
        for line in output.getvalue().splitlines()
    ]

    # Find events belonging to each HTTP request
    first_events = [
        log["event"]
        for log in logs
        if log.get("request_id") == first_id
    ]

    second_events = [
        log["event"]
        for log in logs
        if log.get("request_id") == second_id
    ]

    assert first_events == [
        "redis_cache_miss",
        "http_request",
    ]

    assert second_events == [
        "redis_cache_hit",
        "http_request"
    ]


def test_concurrent_request_ids_are_isolated():
    request_count = 20

    async def send_requests():
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await asyncio.gather(
                *(
                    client.get("/health")
                    for _ in range(request_count)
                )
            )

    # Capture formatted JSON logs
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JSONFormatter())

    app_logger = logging.getLogger("app")
    app_logger.addHandler(handler)

    try:
        responses = asyncio.run(send_requests())
    finally:
        app_logger.removeHandler(handler)
        handler.close()

    # All requests should succeed
    assert all(
        response.status_code == 200
        for response in responses
    )

    request_ids = [
        response.headers["X-Request-ID"]
        for response in responses
    ]

    # Every concurrent request must have a unique ID
    assert len(set(request_ids)) == request_count

    # Verify that each ID is a valid UUID v4
    assert all(
        UUID(request_id).version == 4
        for request_id in request_ids
    )

    logs = [
        json.loads(line)
        for line in output.getvalue().splitlines()
    ]

    http_logs = [
        log
        for log in logs
        if log.get("event") == "http_request"
        and log.get("path") == "/health"
    ]

    assert len(http_logs) == request_count

    # Logged IDs must match HTTP response IDs
    logged_ids = {
        log["request_id"]
        for log in http_logs
    }

    assert logged_ids == set(request_ids)
