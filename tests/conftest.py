import uuid

import httpx
import psycopg
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.db import get_session
from app.main import app

# psycopg wants a plain "postgresql://" URL, not SQLAlchemy's "+driver" form.
RAW_TEST_DSN = settings.test_database_url_sync.replace("postgresql+psycopg://", "postgresql://")

# NullPool: each pytest-asyncio test function runs its own event loop, but a
# pooled asyncpg connection is bound to the loop it was created on -- reusing
# one across tests raises "another operation is in progress". A fresh
# connection per checkout sidesteps that.
_test_engine = create_async_engine(settings.test_database_url, future=True, poolclass=NullPool)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)


async def _override_get_session():
    async with _TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_session] = _override_get_session


@pytest.fixture()
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def new_connection() -> psycopg.Connection:
    """A fresh, independent connection -- used so concurrent test threads
    each get their own real backend process, matching how two separate API
    requests would each get their own connection/transaction."""
    conn = psycopg.connect(RAW_TEST_DSN)
    conn.autocommit = False
    return conn


@pytest.fixture()
def db_conn():
    conn = new_connection()
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture(autouse=True)
def _clean_tables():
    conn = new_connection()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "TRUNCATE appointments, outbox, working_hours, patients, practitioners CASCADE"
        )
    conn.close()
    yield


@pytest.fixture()
def practitioner_id(db_conn) -> uuid.UUID:
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO practitioners (name, specialty) VALUES (%s, %s) RETURNING id",
            ("Dr. Ada Lovelace", "Cardiology"),
        )
        row_id = cur.fetchone()[0]
    db_conn.commit()
    return row_id


@pytest.fixture()
def add_working_hours(db_conn):
    def _add(practitioner_id, day_of_week, start_time, end_time, tz_name):
        with db_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO working_hours "
                "(practitioner_id, day_of_week, start_time, end_time, timezone) "
                "VALUES (%s, %s, %s, %s, %s)",
                (practitioner_id, day_of_week, start_time, end_time, tz_name),
            )
        db_conn.commit()

    return _add


@pytest.fixture()
def patient_ids(db_conn) -> tuple[uuid.UUID, uuid.UUID]:
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO patients (name, email) VALUES (%s, %s) RETURNING id",
            ("Grace Hopper", "grace@example.com"),
        )
        patient_a = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO patients (name, email) VALUES (%s, %s) RETURNING id",
            ("Alan Turing", "alan@example.com"),
        )
        patient_b = cur.fetchone()[0]
    db_conn.commit()
    return patient_a, patient_b
