import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://shortener:dev_password"
    "@localhost:5433/shortener_test"
)

test_database_url = os.getenv(
    "TEST_DATABASE_URL",
    DEFAULT_TEST_DATABASE_URL,
)

if make_url(test_database_url).database != "shortener_test":
    raise RuntimeError("Tests must use the test database!")

os.environ["DATABASE_URL"] = test_database_url

from app.database import engine, get_db
from app.main import app


# Safety check
if engine.url.database != "shortener_test":
    raise RuntimeError("Tests must use the test database!")


@pytest.fixture
def db_connection():
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
def client(db_connection):
    def override_get_db():
        with Session(
            bind=db_connection,
            join_transaction_mode="create_savepoint",
        ) as session:
            yield session


    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()