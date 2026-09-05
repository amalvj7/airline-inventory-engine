import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Booking
from app.schemas.booking import BookingCreate, BookingOut, RebookRequest
from app.services.booking import LegRequest, create_booking
from app.services.cancellation import cancel_booking
from app.services.rebooking import rebook_leg

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("", response_model=BookingOut, status_code=201)
def book(
    payload: BookingCreate,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    booking = create_booking(
        db,
        payload.passenger_id,
        [LegRequest(leg.flight_id, leg.fare_class) for leg in payload.legs],
        idempotency_key=idempotency_key,
    )
    db.commit()
    db.refresh(booking)
    return booking


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: uuid.UUID, db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(404, "Booking not found")
    return booking


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel(booking_id: uuid.UUID, db: Session = Depends(get_db)):
    booking = cancel_booking(db, booking_id)
    db.commit()
    db.refresh(booking)
    return booking


@router.post("/{booking_id}/rebook", response_model=BookingOut)
def rebook(booking_id: uuid.UUID, payload: RebookRequest, db: Session = Depends(get_db)):
    leg = rebook_leg(db, booking_id, payload.leg_id, payload.new_flight_id)
    db.commit()
    booking = db.get(Booking, leg.booking_id)
    db.refresh(booking)
    return booking