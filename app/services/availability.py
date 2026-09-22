import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BLOCKING_STATUSES, WorkingHours

SLOT_MINUTES = 30
UTC = dt_timezone.utc


@dataclass(frozen=True)
class Slot:
    start_utc: datetime
    end_utc: datetime


def _slots_for_local_date(
    start_time: time, end_time: time, local_date: date, tz: ZoneInfo
) -> list[Slot]:
    """Working hours are wall-clock local time; this is the one place that
    turns a specific calendar date's local start/end into UTC instants, so
    every other layer (DB queries, the exclusion constraint) can stay in UTC.
    """
    local_start = datetime.combine(local_date, start_time, tzinfo=tz)
    local_end = datetime.combine(local_date, end_time, tzinfo=tz)

    slots: list[Slot] = []
    cursor = local_start
    step = timedelta(minutes=SLOT_MINUTES)
    while cursor + step <= local_end:
        slots.append(Slot(start_utc=cursor.astimezone(UTC), end_utc=(cursor + step).astimezone(UTC)))
        cursor += step
    return slots


def generate_slots_in_window(
    working_hours: list[WorkingHours], window_start_utc: datetime, window_end_utc: datetime
) -> list[Slot]:
    """Generates every working-hours slot that starts within
    [window_start_utc, window_end_utc), across all supplied working_hours
    rows. Each row's own timezone decides which local calendar date(s) in
    the window map to its day_of_week."""
    slots: list[Slot] = []
    for rule in working_hours:
        tz = ZoneInfo(rule.timezone)
        # A fixed local weekday can start on the previous or next UTC day
        # depending on the offset, so pad by a day on each side and let the
        # window filter below discard anything outside it.
        candidate_dates = {
            (window_start_utc.astimezone(tz) + timedelta(days=offset)).date()
            for offset in (-1, 0, 1)
        }
        for local_date in candidate_dates:
            if local_date.weekday() != rule.day_of_week:
                continue
            for slot in _slots_for_local_date(rule.start_time, rule.end_time, local_date, tz):
                if window_start_utc <= slot.start_utc < window_end_utc:
                    slots.append(slot)
    slots.sort(key=lambda s: s.start_utc)
    return slots


def subtract_booked(slots: list[Slot], booked: list[tuple[datetime, datetime]]) -> list[Slot]:
    def overlaps(slot: Slot, booked_range: tuple[datetime, datetime]) -> bool:
        booked_start, booked_end = booked_range
        return slot.start_utc < booked_end and booked_start < slot.end_utc

    return [slot for slot in slots if not any(overlaps(slot, b) for b in booked)]


async def get_working_hours(session: AsyncSession, practitioner_id: uuid.UUID) -> list[WorkingHours]:
    result = await session.execute(
        select(WorkingHours).where(WorkingHours.practitioner_id == practitioner_id)
    )
    return list(result.scalars().all())


async def get_booked_ranges(
    session: AsyncSession,
    practitioner_id: uuid.UUID,
    window_start_utc: datetime,
    window_end_utc: datetime,
) -> list[tuple[datetime, datetime]]:
    statuses = tuple(s.value for s in BLOCKING_STATUSES)
    result = await session.execute(
        text(
            """
            SELECT lower(time_range), upper(time_range)
            FROM appointments
            WHERE practitioner_id = :practitioner_id
              AND status = ANY(:statuses)
              AND time_range && tstzrange(:window_start, :window_end, '[)')
            """
        ).bindparams(
            practitioner_id=practitioner_id,
            statuses=list(statuses),
            window_start=window_start_utc,
            window_end=window_end_utc,
        )
    )
    return [(row[0], row[1]) for row in result.all()]


async def get_availability(
    session: AsyncSession,
    practitioner_id: uuid.UUID,
    target_date: date,
    requester_tz: ZoneInfo,
) -> tuple[list[Slot], datetime, datetime]:
    """Available slots for the calendar day `target_date` as seen in the
    requester's timezone. Returns the slots plus the UTC window used, so
    callers can localize consistently."""
    window_start_utc = datetime.combine(target_date, time.min, tzinfo=requester_tz).astimezone(UTC)
    window_end_utc = window_start_utc + timedelta(days=1)

    working_hours = await get_working_hours(session, practitioner_id)
    all_slots = generate_slots_in_window(working_hours, window_start_utc, window_end_utc)

    booked = await get_booked_ranges(session, practitioner_id, window_start_utc, window_end_utc)
    free_slots = subtract_booked(all_slots, booked)

    return free_slots, window_start_utc, window_end_utc
