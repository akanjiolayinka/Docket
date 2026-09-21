import uuid
from datetime import date, datetime

from pydantic import BaseModel


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
