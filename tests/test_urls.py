import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

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
