import enum
import uuid
from datetime import datetime, time

from sqlalchemy import CheckConstraint, ForeignKey, String, Time, func, text
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint, TSTZRANGE, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Enum as SAEnum

from app.db import Base


class AppointmentStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    cancelled = "cancelled"
    completed = "completed"


# Statuses that hold a practitioner's slot and must not overlap another
# pending/accepted appointment. Cancelled/completed appointments are excluded
# from the exclusion constraint so the slot frees up.
BLOCKING_STATUSES = (AppointmentStatus.pending, AppointmentStatus.accepted)


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    appointments: Mapped[list["Appointment"]] = relationship(back_populates="patient")


class Practitioner(Base):
    __tablename__ = "practitioners"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    specialty: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    appointments: Mapped[list["Appointment"]] = relationship(back_populates="practitioner")
    working_hours: Mapped[list["WorkingHours"]] = relationship(back_populates="practitioner")


class WorkingHours(Base):
    """A recurring weekly working-hours rule for a practitioner.

    start_time/end_time are wall-clock local time in `timezone` (an IANA
    name, e.g. "America/New_York") -- not UTC. The slot generator converts
    them to UTC per calendar date, since a fixed local time is a different
    UTC instant depending on the date (DST).
    """

    __tablename__ = "working_hours"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    practitioner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("practitioners.id"), nullable=False
    )
    # date.weekday() convention: 0 = Monday ... 6 = Sunday.
    day_of_week: Mapped[int] = mapped_column(nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    practitioner: Mapped["Practitioner"] = relationship(back_populates="working_hours")

    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="working_hours_day_of_week_range"),
        CheckConstraint("start_time < end_time", name="working_hours_start_before_end"),
    )


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False
    )
    practitioner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("practitioners.id"), nullable=False
    )
    # Always UTC. Stored as tstzrange so the exclusion constraint can use
    # the range overlap operator (&&) directly.
    time_range = mapped_column(TSTZRANGE, nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        SAEnum(AppointmentStatus, name="appointment_status", native_enum=True),
        nullable=False,
        default=AppointmentStatus.pending,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    patient: Mapped["Patient"] = relationship(back_populates="appointments")
    practitioner: Mapped["Practitioner"] = relationship(back_populates="appointments")

    __table_args__ = (
        # The actual double-booking guarantee. Two rows for the same
        # practitioner with overlapping time_range can both exist only if
        # neither is pending/accepted (the WHERE clause) -- app-level checks
        # are just a nicer error message in front of this.
        ExcludeConstraint(
            ("practitioner_id", "="),
            ("time_range", "&&"),
            using="gist",
            where=text(
                "status IN ("
                + ", ".join(f"'{s.value}'" for s in BLOCKING_STATUSES)
                + ")"
            ),
            name="appointments_no_overlap_per_practitioner",
        ),
    )


class Outbox(Base):
    """Transactional outbox: written in the same transaction as the booking
    write it accompanies. A separate worker polls rows where
    published_at IS NULL and publishes them to RabbitMQ -- nothing in the
    request path talks to the queue directly, so a rolled-back transaction
    never leaves an event with no matching booking."""

    __tablename__ = "outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
