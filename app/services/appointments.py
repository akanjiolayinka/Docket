import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, AppointmentStatus, Outbox, Patient, Practitioner

EXCLUSION_CONSTRAINT_NAME = "appointments_no_overlap_per_practitioner"


class SlotUnavailableError(Exception):
    """Raised when the exclusion constraint rejects the insert/update --
    someone else holds an overlapping slot for this practitioner."""


class PatientNotFoundError(Exception):
    pass


class PractitionerNotFoundError(Exception):
    pass


class AppointmentNotFoundError(Exception):
    pass


class AppointmentNotModifiableError(Exception):
    """The appointment is cancelled/completed and can't be changed further."""


def _to_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc)


def _is_exclusion_violation(error: IntegrityError) -> bool:
    # asyncpg/psycopg surface the constraint name in the original driver
    # error; matching on it (rather than treating every IntegrityError as a
    # conflict) keeps a genuine bug -- e.g. a bad foreign key -- from being
    # reported to the client as a 409.
    return EXCLUSION_CONSTRAINT_NAME in str(error.orig)


async def create_appointment(
    session: AsyncSession,
    patient_id: uuid.UUID,
    practitioner_id: uuid.UUID,
    start: datetime,
    end: datetime,
) -> Appointment:
    if await session.get(Patient, patient_id) is None:
        raise PatientNotFoundError(str(patient_id))
    if await session.get(Practitioner, practitioner_id) is None:
        raise PractitionerNotFoundError(str(practitioner_id))

    appointment = Appointment(
        patient_id=patient_id,
        practitioner_id=practitioner_id,
        time_range=Range(_to_utc(start), _to_utc(end), bounds="[)"),
        status=AppointmentStatus.pending,
    )
    session.add(appointment)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        if _is_exclusion_violation(exc):
            raise SlotUnavailableError from exc
        raise

    # Same transaction as the booking write -- never published from here
    # directly. A separate worker polls this table (Phase 6).
    session.add(
        Outbox(
            event_type="email_confirmation",
            payload={
                "appointment_id": str(appointment.id),
                "patient_id": str(patient_id),
                "practitioner_id": str(practitioner_id),
                "start_utc": _to_utc(start).isoformat(),
                "end_utc": _to_utc(end).isoformat(),
            },
        )
    )
    await session.commit()
    await session.refresh(appointment)
    return appointment


async def get_appointment(session: AsyncSession, appointment_id: uuid.UUID) -> Appointment:
    appointment = await session.get(Appointment, appointment_id)
    if appointment is None:
        raise AppointmentNotFoundError(str(appointment_id))
    return appointment


async def update_appointment(
    session: AsyncSession,
    appointment_id: uuid.UUID,
    *,
    status: AppointmentStatus | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> Appointment:
    appointment = await get_appointment(session, appointment_id)

    if appointment.status in (AppointmentStatus.cancelled, AppointmentStatus.completed):
        raise AppointmentNotModifiableError(
            f"appointment {appointment_id} is {appointment.status.value} and cannot be modified"
        )

    if status is not None:
        appointment.status = status

    if start is not None and end is not None:
        appointment.time_range = Range(_to_utc(start), _to_utc(end), bounds="[)")

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        if _is_exclusion_violation(exc):
            raise SlotUnavailableError from exc
        raise

    await session.commit()
    await session.refresh(appointment)
    return appointment
