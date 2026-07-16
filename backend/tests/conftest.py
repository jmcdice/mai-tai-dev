"""Shared test fixtures.

Tests run against a real Postgres database (DATABASE_URL, defaulting to a
local maitai_test DB). Schema is created from the SQLAlchemy models once per
session; every test starts with truncated tables.

All tests use the synchronous Starlette TestClient. A single session-scoped
client keeps the app (and its asyncpg pool) on one event loop, which avoids
"attached to a different loop" errors across tests.
"""

import os

# Configure the app BEFORE anything imports app.core.config (get_settings is
# cached at first call).
os.environ.setdefault(
    "DATABASE_URL", "postgresql://maitai@localhost:5432/maitai_test"
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DEBUG", "false")
# The scheduler loop is driven explicitly in tests via tick()
os.environ.setdefault("SCHEDULER_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

import app.models  # noqa: F401  (register all models on Base.metadata)
from app.api.v1.auth import limiter as auth_limiter
from app.db.base import Base
from app.main import app

# Rate limits (3/min on register etc.) would trip across tests
auth_limiter.enabled = False

# Sync engine for schema management and test data manipulation
sync_engine = create_engine(os.environ["DATABASE_URL"])


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    """Create all tables once for the test session.

    The schema is dropped wholesale (not via metadata.drop_all) so tables
    removed from the models can't linger and break FK ordering.
    """
    with sync_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(sync_engine)
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    """Start every test with empty tables."""
    with sync_engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture(scope="session")
def client():
    """One TestClient (and thus one event loop) for the whole session."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def register_user(client: TestClient, email: str = "user@example.com",
                  password: str = "test-password-123", name: str = "Test User") -> dict:
    """Register a user and return the registration payload (user/workspace/api_key)."""
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": name},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def login_user(client: TestClient, email: str = "user@example.com",
               password: str = "test-password-123") -> dict:
    """Login and return the token payload."""
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_a(client) -> dict:
    """A registered + logged-in user with their provisioned workspace and key."""
    reg = register_user(client, email="a@example.com")
    tokens = login_user(client, email="a@example.com")
    return {
        "registration": reg,
        "token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "workspace_id": reg["workspace"]["id"],
        "api_key": reg["api_key"]["key"],  # user-level key
    }


@pytest.fixture
def user_b(client) -> dict:
    """A second registered + logged-in user."""
    reg = register_user(client, email="b@example.com")
    tokens = login_user(client, email="b@example.com")
    return {
        "registration": reg,
        "token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "workspace_id": reg["workspace"]["id"],
        "api_key": reg["api_key"]["key"],
    }
