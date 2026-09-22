from datetime import date, datetime, timezone

from app.models import WorkingHours
from app.services.availability import generate_slots_in_window, subtract_booked
from zoneinfo import ZoneInfo


def test_generate_slots_in_window_produces_30_minute_slots():
    rule = WorkingHours(
        day_of_week=0,  # Monday
        start_time=datetime(2030, 1, 7, 9, 0).time(),
        end_time=datetime(2030, 1, 7, 12, 0).time(),
        timezone="UTC",
    )
    window_start = datetime(2030, 1, 7, tzinfo=timezone.utc)
    window_end = datetime(2030, 1, 8, tzinfo=timezone.utc)

    slots = generate_slots_in_window([rule], window_start, window_end)

    assert len(slots) == 6
    assert slots[0].start_utc == datetime(2030, 1, 7, 9, 0, tzinfo=timezone.utc)
    assert slots[0].end_utc == datetime(2030, 1, 7, 9, 30, tzinfo=timezone.utc)
    assert slots[-1].end_utc == datetime(2030, 1, 7, 12, 0, tzinfo=timezone.utc)


def test_subtract_booked_removes_overlapping_slots():
    rule = WorkingHours(
        day_of_week=0,
        start_time=datetime(2030, 1, 7, 9, 0).time(),
        end_time=datetime(2030, 1, 7, 10, 0).time(),
        timezone="UTC",
    )
    window_start = datetime(2030, 1, 7, tzinfo=timezone.utc)
    window_end = datetime(2030, 1, 8, tzinfo=timezone.utc)
    slots = generate_slots_in_window([rule], window_start, window_end)
    assert len(slots) == 2

    booked = [
        (
            datetime(2030, 1, 7, 9, 0, tzinfo=timezone.utc),
            datetime(2030, 1, 7, 9, 30, tzinfo=timezone.utc),
        )
    ]
    remaining = subtract_booked(slots, booked)

    assert len(remaining) == 1
    assert remaining[0].start_utc == datetime(2030, 1, 7, 9, 30, tzinfo=timezone.utc)


async def test_availability_endpoint_lists_and_subtracts_booked_slots(
    client, practitioner_id, patient_ids, add_working_hours, db_conn
):
    patient_a, _ = patient_ids
    target_date = date(2030, 1, 7)
    assert target_date.weekday() == 0  # Monday, matches day_of_week below

    add_working_hours(practitioner_id, 0, "09:00", "12:00", "UTC")

    resp = await client.get(
        f"/practitioners/{practitioner_id}/availability",
        params={"date": "2030-01-07", "tz": "UTC"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["slots"]) == 6

    # Book the first slot directly against the DB (same guarantee the
    # exclusion constraint relies on) and confirm it disappears from
    # availability.
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO appointments (patient_id, practitioner_id, time_range, status) "
            "VALUES (%s, %s, tstzrange(%s, %s, '[)'), 'accepted')",
            (patient_a, practitioner_id, "2030-01-07T09:00:00+00", "2030-01-07T09:30:00+00"),
        )
    db_conn.commit()

    resp = await client.get(
        f"/practitioners/{practitioner_id}/availability",
        params={"date": "2030-01-07", "tz": "UTC"},
    )
    body = resp.json()
    assert len(body["slots"]) == 5
    starts = {slot["start_utc"] for slot in body["slots"]}
    assert "2030-01-07T09:00:00Z" not in starts


async def test_availability_converts_timezones_at_the_api_boundary(
    client, practitioner_id, add_working_hours
):
    """Practitioner's working hours are in America/New_York; the patient
    requests availability in Asia/Kolkata. Business logic (slot generation)
    stays in UTC throughout -- only the request's `date` and the response's
    `*_local` fields cross the timezone boundary."""
    local_date = date(2030, 1, 7)
    assert local_date.weekday() == 0  # Monday

    add_working_hours(practitioner_id, 0, "09:00", "11:00", "America/New_York")

    resp = await client.get(
        f"/practitioners/{practitioner_id}/availability",
        params={"date": "2030-01-07", "tz": "Asia/Kolkata"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["timezone"] == "Asia/Kolkata"
    assert len(body["slots"]) == 4  # 09:00-11:00 local in 30-min increments

    first_slot = body["slots"][0]
    start_utc = datetime.fromisoformat(first_slot["start_utc"].replace("Z", "+00:00"))
    start_local = datetime.fromisoformat(first_slot["start_local"])

    # 09:00 America/New_York in January (EST, UTC-5) is 14:00 UTC.
    assert start_utc == datetime(2030, 1, 7, 14, 0, tzinfo=timezone.utc)
    # 14:00 UTC in Asia/Kolkata (UTC+5:30) is 19:30 the same day.
    assert start_local.astimezone(ZoneInfo("Asia/Kolkata")) == datetime(
        2030, 1, 7, 19, 30, tzinfo=ZoneInfo("Asia/Kolkata")
    )


async def test_availability_unknown_timezone_is_rejected(client, practitioner_id):
    resp = await client.get(
        f"/practitioners/{practitioner_id}/availability",
        params={"date": "2030-01-07", "tz": "Not/A_Timezone"},
    )
    assert resp.status_code == 400


async def test_availability_unknown_practitioner_is_404(client):
    resp = await client.get(
        "/practitioners/00000000-0000-0000-0000-000000000000/availability",
        params={"date": "2030-01-07"},
    )
    assert resp.status_code == 404
