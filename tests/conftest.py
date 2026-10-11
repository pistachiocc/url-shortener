import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

# Configure the test database before importing the app.
os.environ["DATABASE_URL"] = (
    "postgresql+psycopg://shortener:dev_password"
    "@localhost:5433/shortener_test"
)

from app.database import engine
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client

    # Clean up the test database after each test.
    with engine.begin() as conn:
        conn.execute(
            text("TRUNCATE TABLE urls RESTART IDENTITY CASCADE")
        )