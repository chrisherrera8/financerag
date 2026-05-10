import hashlib
import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from tests.fixtures.chunk_fixtures import make_paragraph_chunk  # noqa: F401

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://financerag:financerag@localhost:5432/financerag_test",
)


def _maintenance_dsn(db_url: str) -> str:
    """Swap the database name for 'postgres' so we can CREATE DATABASE."""
    parsed = urlparse(db_url)
    return urlunparse(parsed._replace(scheme="postgresql", path="/postgres"))


@pytest.fixture(scope="session", autouse=True)
def create_test_database():
    dsn = _maintenance_dsn(TEST_DATABASE_URL)
    db_name = urlparse(TEST_DATABASE_URL).path.lstrip("/")
    with psycopg.connect(dsn, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{db_name}"')


@pytest.fixture(scope="session")
def engine(create_test_database):
    # Override DATABASE_URL so migrations/env.py targets the test DB, not prod.
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    eng = create_engine(TEST_DATABASE_URL)
    cfg = Config(str(_PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    conn = engine.connect()
    trans = conn.begin()
    sess = Session(bind=conn, join_transaction_mode="create_savepoint")
    yield sess
    sess.close()
    trans.rollback()
    conn.close()


@pytest.fixture()
def data_dir(tmp_path):
    d = tmp_path / "data" / "AAPL" / "10-K" / "0000320193-24-000123"
    d.mkdir(parents=True)
    return tmp_path / "data"


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
