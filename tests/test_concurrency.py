"""Proves the double-booking guarantee holds under real concurrency.

This deliberately does not go through the app layer: it opens two
independent database connections (like two separate API requests would)
and races them against the actual Postgres EXCLUDE USING GIST constraint,
since that constraint -- not any app-level check -- is what the schema
relies on for correctness.
"""

import threading

import psycopg
import pytest

from tests.conftest import new_connection

TIME_RANGE = "['2030-01-01T10:00:00+00', '2030-01-01T10:30:00+00')"
OVERLAPPING_TIME_RANGE = "['2030-01-01T10:15:00+00', '2030-01-01T10:45:00+00')"
DISTINCT_TIME_RANGE = "['2030-01-01T11:00:00+00', '2030-01-01T11:30:00+00')"

INSERT_SQL = (
    "INSERT INTO appointments (patient_id, practitioner_id, time_range, status) "
    "VALUES (%s, %s, %s, 'pending')"
)


def _book(practitioner_id, patient_id, time_range, barrier, results, index, hold_seconds=0.0):
    """Runs in its own thread with its own connection/transaction."""
    conn = new_connection()
    try:
        with conn.cursor() as cur:
            barrier.wait()  # line both threads up so the inserts race
            try:
                cur.execute(INSERT_SQL, (patient_id, practitioner_id, time_range))
            except (psycopg.errors.ExclusionViolation, psycopg.errors.DeadlockDetected):
                # Under true concurrency Postgres may resolve the race either
                # by rejecting the second insert outright (ExclusionViolation)
                # or, if both transactions reach the check at once, by
                # aborting one to break a deadlock (DeadlockDetected) --
                # either way exactly one side loses, which is the guarantee
                # under test.
                conn.rollback()
                results[index] = "rejected"
                return
            if hold_seconds:
                import time

                time.sleep(hold_seconds)
        conn.commit()
        results[index] = "accepted"
    except Exception as exc:  # pragma: no cover - surfaced via assertion
        conn.rollback()
        results[index] = f"error: {exc}"
    finally:
        conn.close()


def test_two_concurrent_overlapping_bookings_only_one_succeeds(practitioner_id, patient_ids):
    patient_a, patient_b = patient_ids
    barrier = threading.Barrier(2)
    results = [None, None]

    threads = [
        threading.Thread(
            target=_book,
            args=(practitioner_id, patient_a, TIME_RANGE, barrier, results, 0, 0.3),
        ),
        threading.Thread(
            target=_book,
            args=(practitioner_id, patient_b, OVERLAPPING_TIME_RANGE, barrier, results, 1, 0.0),
        ),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert results.count("accepted") == 1, results
    assert results.count("rejected") == 1, results

    conn = new_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM appointments WHERE practitioner_id = %s", (practitioner_id,)
        )
        rows = cur.fetchall()
    conn.close()
    assert len(rows) == 1, "exactly one appointment row should exist after the race"


def test_two_concurrent_non_overlapping_bookings_both_succeed(practitioner_id, patient_ids):
    patient_a, patient_b = patient_ids
    barrier = threading.Barrier(2)
    results = [None, None]

    threads = [
        threading.Thread(
            target=_book,
            args=(practitioner_id, patient_a, TIME_RANGE, barrier, results, 0),
        ),
        threading.Thread(
            target=_book,
            args=(practitioner_id, patient_b, DISTINCT_TIME_RANGE, barrier, results, 1),
        ),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert results == ["accepted", "accepted"], results


def test_sequential_overlapping_booking_after_cancellation_succeeds(practitioner_id, patient_ids):
    """Once the first booking is cancelled, its slot is no longer blocking --
    proving the WHERE status IN ('pending','accepted') clause on the
    constraint behaves as intended."""
    patient_a, patient_b = patient_ids
    conn = new_connection()
    with conn.cursor() as cur:
        cur.execute(INSERT_SQL, (patient_a, practitioner_id, TIME_RANGE))
    conn.commit()

    with conn.cursor() as cur:
        with pytest.raises(psycopg.errors.ExclusionViolation):
            cur.execute(INSERT_SQL, (patient_b, practitioner_id, OVERLAPPING_TIME_RANGE))
    conn.rollback()

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE appointments SET status = 'cancelled' WHERE practitioner_id = %s",
            (practitioner_id,),
        )
        cur.execute(INSERT_SQL, (patient_b, practitioner_id, OVERLAPPING_TIME_RANGE))
    conn.commit()
    conn.close()
