import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Appointment
from app.schemas import AppointmentCreate, AppointmentRead, AppointmentUpdate
from app.services import appointments as appointments_service

router = APIRouter(prefix="/appointments", tags=["appointments"])


def _to_read(appointment: Appointment) -> AppointmentRead:
    return AppointmentRead(
        id=appointment.id,
        patient_id=appointment.patient_id,
        practitioner_id=appointment.practitioner_id,
        start_utc=appointment.time_range.lower,
        end_utc=appointment.time_range.upper,
        status=appointment.status,
        created_at=appointment.created_at,
    )


@router.post("", response_model=AppointmentRead, status_code=201)
async def book_appointment(
    body: AppointmentCreate, session: AsyncSession = Depends(get_session)
) -> AppointmentRead:
    try:
        appointment = await appointments_service.create_appointment(
            session, body.patient_id, body.practitioner_id, body.start, body.end
        )
    except appointments_service.PatientNotFoundError:
        raise HTTPException(status_code=404, detail="Patient not found")
    except appointments_service.PractitionerNotFoundError:
        raise HTTPException(status_code=404, detail="Practitioner not found")
    except appointments_service.SlotUnavailableError:
        raise HTTPException(status_code=409, detail="This slot is no longer available")
    return _to_read(appointment)


@router.get("/{appointment_id}", response_model=AppointmentRead)
async def read_appointment(
    appointment_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> AppointmentRead:
    try:
        appointment = await appointments_service.get_appointment(session, appointment_id)
    except appointments_service.AppointmentNotFoundError:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return _to_read(appointment)


@router.patch("/{appointment_id}", response_model=AppointmentRead)
async def patch_appointment(
    appointment_id: uuid.UUID,
    body: AppointmentUpdate,
    session: AsyncSession = Depends(get_session),
) -> AppointmentRead:
    try:
        appointment = await appointments_service.update_appointment(
            session,
            appointment_id,
            status=body.status,
            start=body.start,
            end=body.end,
        )
    except appointments_service.AppointmentNotFoundError:
        raise HTTPException(status_code=404, detail="Appointment not found")
    except appointments_service.AppointmentNotModifiableError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except appointments_service.SlotUnavailableError:
        raise HTTPException(status_code=409, detail="This slot is no longer available")
    return _to_read(appointment)
