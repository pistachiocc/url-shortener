import re

import pytest
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