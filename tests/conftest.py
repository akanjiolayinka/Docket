import uuid

import psycopg
import pytest

from app.config import settings

# psycopg wants a plain "postgresql://" URL, not SQLAlchemy's "+driver" form.
RAW_TEST_DSN = settings.test_database_url_sync.replace("postgresql+psycopg://", "postgresql://")


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
        cur.execute("TRUNCATE appointments, patients, practitioners CASCADE")
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
