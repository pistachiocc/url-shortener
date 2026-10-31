import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from psycopg.errors import NotNullViolation

from sqlalchemy.orm import Session
from app.models import URL


def test_create_short_url(client):
    response = client.post(
        "/api/v1/urls",
        json={"long_url": "https://example.com/articles/123"}
    )

    assert response.status_code == 201

    data = response.json()
    assert re.fullmatch(r"[a-zA-Z0-9]{8}", data["code"])
    assert data["short_url"].endswith(data["code"])


def test_redirect(client):
    original_url = "https://example.com/articles/123"

    response = client.post(
        "/api/v1/urls",
        json={"long_url": original_url},
    )

    assert response.status_code == 201
    assert response.json()["expires_at"] is None

    code = response.json()["code"]

    response = client.get(
        f"/{code}",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == original_url


def test_not_found(client):
    response = client.get("/missing0")

    assert response.status_code == 404


def test_duplicate_short_code(client, db_connection):
    with Session(
        bind=db_connection,
        join_transaction_mode="create_savepoint",
    ) as session:
        session.add(
            URL(
                short_code="abc12345",
                original_url="https://example.com/first",
            )
        )
        session.commit()

        session.add(
            URL(
                short_code="abc12345",
                original_url="https://example.com/second",
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()

        session.rollback()


def test_create_retires_on_short_code_collision(
    client, db_connection, monkeypatch
):
    existing_code = "abc12345"
    new_code = "xyz67890"

    # Insert an existing short code
    with Session(
        bind=db_connection,
        join_transaction_mode="create_savepoint",
    ) as session:
        session.add(
            URL(
                short_code=existing_code,
                original_url="https://example.com/existing",
            )
        )
        session.commit()

    # Force the first generated code to collide
    generated_chars = iter(existing_code + new_code)
    calls = 0

    def fake_choice(alphabet):
        nonlocal calls
        calls += 1
        return next(generated_chars)

    monkeypatch.setattr(
        "app.main.secrets.choice",
        fake_choice,
    )

    response = client.post(
        "/api/v1/urls",
        json={"long_url": "https://example.com/new"},
    )

    assert response.status_code == 201
    assert response.json()["code"] == new_code
    assert calls == 16


def test_create_does_not_retry_other_integrity_errors(
    client, monkeypatch
):
    calls = 0

    def failing_commit(session):
        nonlocal calls
        calls += 1

        raise IntegrityError(
            statement="INSERT INTO urls ...",
            params={},
            orig=NotNullViolation(
                "Simulated NOT NULL violation"
            ),
        )

    monkeypatch.setattr(
        Session,
        "commit",
        failing_commit,
    )

    with pytest.raises(IntegrityError):
        client.post(
            "/api/v1/urls",
            json={"long_url": "https://example.com"},
        )

    assert calls == 1


def test_create_returns_503_after_five_collisions(
    client, db_connection, monkeypatch
):
    existing_code = "abc12345"

    # Insert an existing short code
    with Session(
        bind=db_connection,
        join_transaction_mode="create_savepoint",
    ) as session:
        session.add(
            URL(
                short_code=existing_code,
                original_url="https://example.com/existing",
            )
        )
        session.commit()

    calls = 0

    def fake_choice(alphabet):
        nonlocal calls
        char = existing_code[calls % len(existing_code)]
        calls += 1
        return char

    # Every attempt generates the same short code
    monkeypatch.setattr(
        "app.main.secrets.choice",
        fake_choice,
    )

    response = client.post(
        "/api/v1/urls",
        json={"long_url": "https://example.com/new"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Could not generate unique short code"

    # 8 characters per attempt * 5 attempts
    assert calls == 40


def test_expiring_url(client):
    response = client.post(
        "api/v1/urls",
        json={
            "long_url": "http://example.com",
            "expires_in_seconds": 3600,
        },
    )

    assert response.status_code == 201

    data = response.json()
    assert data["expires_at"] is not None

    response = client.get(
        f"/{data['code']}",
        follow_redirects=False,
    )

    assert response.status_code == 302


def test_expired_url(client, db_connection):
    response = client.post(
        "api/v1/urls",
        json={
            "long_url": "http://example.com",
            "expires_in_seconds": 3600,
        },
    )

    assert response.status_code == 201
    code = response.json()["code"]

    with Session(
        bind=db_connection,
        join_transaction_mode="create_savepoint",
    ) as session:
        session.execute(
            update(URL)
            .where(URL.short_code == code)
            .values(
                expires_at=datetime.now(timezone.utc)
                - timedelta(seconds=1)
            )
        )
        session.commit()

    response = client.get(
        f"/{code}",
        follow_redirects=False,
    )

    assert response.status_code == 410
    assert response.json()["detail"] == "URL has expired"


@pytest.mark.parametrize(
    "ttl",
    [0, -1, 31_536_001],
)
def test_invalid_expiration(client, ttl):
    response = client.post(
        "api/v1/urls",
        json={
            "long_url": "http://example.com",
            "expires_in_seconds": ttl,
        },
    )

    assert response.status_code == 422


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
