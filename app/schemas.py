import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator, model_validator

from app.models import AppointmentStatus


class AvailabilitySlot(BaseModel):
    start_utc: datetime
    end_utc: datetime
    start_local: datetime
    end_local: datetime


class AvailabilityResponse(BaseModel):
    practitioner_id: uuid.UUID
    date: date
    timezone: str
    slots: list[AvailabilitySlot]


def _require_tz_aware(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("datetime must include a UTC offset")
    return v


class AppointmentCreate(BaseModel):
    patient_id: uuid.UUID
    practitioner_id: uuid.UUID
    start: datetime
    end: datetime

    _check_start = field_validator("start")(_require_tz_aware)
    _check_end = field_validator("end")(_require_tz_aware)

    @model_validator(mode="after")
    def _check_start_before_end(self) -> "AppointmentCreate":
        if self.start >= self.end:
            raise ValueError("start must be before end")
        return self


class AppointmentUpdate(BaseModel):
    """PATCH body for cancelling or rescheduling. `status` may only be set
    to `cancelled` here -- other transitions go through dedicated flows
    (e.g. a future practitioner-approval endpoint for pending -> accepted)."""

    status: AppointmentStatus | None = None
    start: datetime | None = None
    end: datetime | None = None

    _check_start = field_validator("start")(_require_tz_aware)
    _check_end = field_validator("end")(_require_tz_aware)

    @model_validator(mode="after")
    def _check_consistent(self) -> "AppointmentUpdate":
        if (self.start is None) != (self.end is None):
            raise ValueError("start and end must be provided together")
        if self.start is not None and self.end is not None and self.start >= self.end:
            raise ValueError("start must be before end")
        if self.status is not None and self.status != AppointmentStatus.cancelled:
            raise ValueError("status may only be set to 'cancelled' via this endpoint")
        return self


class AppointmentRead(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    practitioner_id: uuid.UUID
    start_utc: datetime
    end_utc: datetime
    status: AppointmentStatus
    created_at: datetime
