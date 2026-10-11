import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Configure the test database before importing the app.
os.environ["DATABASE_URL"] = (
    "postgresql+psycopg://shortener:dev_password"
    "@localhost:5433/shortener_test"
)

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