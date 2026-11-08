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
