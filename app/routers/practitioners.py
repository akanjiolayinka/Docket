import uuid
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Practitioner
from app.schemas import AvailabilityResponse, AvailabilitySlot
from app.services import availability as availability_service

router = APIRouter(prefix="/practitioners", tags=["practitioners"])


@router.get("/{practitioner_id}/availability", response_model=AvailabilityResponse)
async def get_practitioner_availability(
    practitioner_id: uuid.UUID,
    date: date = Query(..., description="Calendar date, in the `tz` timezone, to check"),
    tz: str = Query("UTC", description="IANA timezone the `date` and response times are in"),
    session: AsyncSession = Depends(get_session),
) -> AvailabilityResponse:
    target_date = date
    try:
        requester_tz = ZoneInfo(tz)
    except ZoneInfoNotFoundError:
        raise HTTPException(status_code=400, detail=f"Unknown timezone: {tz!r}")

    practitioner = await session.get(Practitioner, practitioner_id)
    if practitioner is None:
        raise HTTPException(status_code=404, detail="Practitioner not found")

    slots, _, _ = await availability_service.get_availability(
        session, practitioner_id, target_date, requester_tz
    )

    return AvailabilityResponse(
        practitioner_id=practitioner_id,
        date=target_date,
        timezone=tz,
        slots=[
            AvailabilitySlot(
                start_utc=slot.start_utc,
                end_utc=slot.end_utc,
                start_local=slot.start_utc.astimezone(requester_tz),
                end_local=slot.end_utc.astimezone(requester_tz),
            )
            for slot in slots
        ],
    )
