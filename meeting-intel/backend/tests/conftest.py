"""Shared test fixtures.

Tests run against a real Postgres (the compose `db` service, database `meeting_intel_test`).
Env vars are set before the app is imported so Settings picks them up.
"""
import os

TEST_DB_URL = os.environ.get(
    "DATABASE_URL_TEST", "postgresql+psycopg://mi:mi@localhost:5433/meeting_intel_test"
)
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["DATABASE_URL_TEST"] = TEST_DB_URL
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret")
os.environ.setdefault("AWS_REGION", "ap-south-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
for _k in ("ADMIN_EMAIL", "ADMIN_PASSWORD"):
    os.environ.pop(_k, None)

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_db  # noqa: E402
from app.errors import ApiError  # noqa: E402
from app.main import create_app  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DB_URL, future=True)
    alembic_ini = BACKEND_DIR / "alembic.ini"
    if alembic_ini.exists():
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(alembic_ini))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
        command.upgrade(cfg, "head")
    yield eng
    eng.dispose()


def _truncate_all(conn) -> None:
    tables = [
        r[0]
        for r in conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'")
        )
    ]
    if tables:
        conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"))


@pytest.fixture
def db(engine) -> Session:
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        with engine.begin() as conn:
            _truncate_all(conn)


@pytest.fixture(autouse=True)
def _clear_caches():
    """Response caches must not leak between tests."""
    yield
    from app.api.routers.dashboard import clear_stats_cache
    from app.ratelimit import ai_limiter

    clear_stats_cache()
    ai_limiter.reset()


@pytest.fixture
def settings_override():
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


def _client_for(app, db) -> TestClient:
    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def app(db):
    return create_app()


@pytest.fixture
def client(app, db) -> TestClient:
    return _client_for(app, db)


DEFAULT_PASSWORD = "correct horse battery"


@pytest.fixture
def make_user(db):
    """Create a user directly in the DB. Returns the User row."""
    from app.auth.security import hash_password
    from app.models import User

    def _make(email: str, password: str = DEFAULT_PASSWORD, role: str = "user", **kw) -> User:
        u = User(
            email=email.lower(),
            name=kw.pop("name", email.split("@")[0].title()),
            password_hash=hash_password(password),
            role=role,
            **kw,
        )
        db.add(u)
        db.commit()
        return u

    return _make


def login(client: TestClient, email: str, password: str = DEFAULT_PASSWORD):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r


@pytest.fixture
def admin_client(app, db, make_user) -> TestClient:
    make_user("admin@example.com", role="admin", access_scope="all", can_download=True)
    c = _client_for(app, db)
    login(c, "admin@example.com")
    return c


@pytest.fixture
def client_with_test_routes(db) -> TestClient:
    app = create_app()

    @app.get("/api/_boom")
    def _boom():
        raise ApiError(418, "teapot", "boom")

    @app.get("/api/_typed")
    def _typed(n: int):
        return {"n": n}

    @app.get("/api/_crash")
    def _crash():
        raise RuntimeError("secret")

    return _client_for(app, db)
