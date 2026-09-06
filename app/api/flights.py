import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Flight, FlightInventory
from app.schemas.flight import FlightCreate, FlightOut, OverbookingUpdate
from app.schemas.ops import BumpOut
from app.services.bump import resolve_oversold_flight
from app.services.overbooking import set_overbooking_factor

router = APIRouter(prefix="/flights", tags=["flights"])


@router.post("", response_model=FlightOut, status_code=201)
def create_flight(payload: FlightCreate, db: Session = Depends(get_db)):
    if payload.arrival_time <= payload.departure_time:
        raise HTTPException(400, "arrival_time must be after departure_time")

    flight = Flight(
        flight_number=payload.flight_number,
        origin=payload.origin.upper(),
        destination=payload.destination.upper(),
        departure_time=payload.departure_time,
        arrival_time=payload.arrival_time,
    )
    flight.inventory = FlightInventory(
        physical_capacity=payload.physical_capacity,
        overbooking_factor=payload.overbooking_factor,
        booking_limit=FlightInventory.compute_booking_limit(
            payload.physical_capacity, payload.overbooking_factor
        ),
        booked_count=0,
    )
    db.add(flight)
    db.commit()
    db.refresh(flight)
    return flight


@router.get("", response_model=list[FlightOut])
def list_flights(db: Session = Depends(get_db)):
    return db.execute(select(Flight).order_by(Flight.flight_number)).scalars().all()


@router.get("/{flight_id}", response_model=FlightOut)
def get_flight(flight_id: uuid.UUID, db: Session = Depends(get_db)):
    flight = db.get(Flight, flight_id)
    if flight is None:
        raise HTTPException(404, "Flight not found")
    return flight


@router.patch("/{flight_id}/overbooking", response_model=FlightOut)
def update_overbooking(
    flight_id: uuid.UUID, payload: OverbookingUpdate, db: Session = Depends(get_db)
):
    set_overbooking_factor(db, flight_id, payload.overbooking_factor)
    db.commit()
    return db.get(Flight, flight_id)


@router.post("/{flight_id}/bump", response_model=BumpOut)
def bump(flight_id: uuid.UUID, db: Session = Depends(get_db)):
    result = resolve_oversold_flight(db, flight_id)
    db.commit()
    return BumpOut(
        flight_id=result.flight_id,
        overage=result.overage,
        bumped_leg_ids=result.bumped_leg_ids,
        cascaded_leg_ids=result.cascaded_leg_ids,
    )