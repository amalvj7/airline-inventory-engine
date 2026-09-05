import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking, BookingLeg, Flight, Passenger
from app.models.enums import BookingStatus, FareClass, LegStatus
from app.repositories.inventory import lock_inventories
from app.services.exceptions import (
    FlightNotFound,
    InvalidItinerary,
    LegUnavailable,
    PassengerNotFound,
)


@dataclass(frozen=True)
class LegRequest:
    flight_id: uuid.UUID
    fare_class: FareClass = FareClass.M


def create_booking(
    session: Session,
    passenger_id: uuid.UUID,
    legs: list[LegRequest],
    idempotency_key: str | None = None,
) -> Booking:
    """
    Claim one seat on every leg of an itinerary, atomically.

    Either all legs are reserved and the booking is confirmed, or nothing
    changes and an exception propagates, rolling the transaction back.
    """
    if not legs:
        raise InvalidItinerary("Itinerary must contain at least one leg")

    flight_ids = [leg.flight_id for leg in legs]
    if len(set(flight_ids)) != len(flight_ids):
        raise InvalidItinerary("An itinerary cannot use the same flight twice")

    if idempotency_key:
        existing = session.execute(
            select(Booking).where(Booking.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing:
            return existing

    passenger = session.get(Passenger, passenger_id)
    if passenger is None:
        raise PassengerNotFound(passenger_id)

    # Lock every leg's inventory row before any availability decision is made.
    inventories = lock_inventories(session, flight_ids)

    flights = {
        f.id: f
        for f in session.execute(select(Flight).where(Flight.id.in_(flight_ids)))
        .scalars()
        .all()
    }

    for fid in flight_ids:
        if fid not in inventories or fid not in flights:
            raise FlightNotFound(fid)

    # Check all legs before mutating any of them.
    for fid in flight_ids:
        inv = inventories[fid]
        if not inv.is_available:
            raise LegUnavailable(
                fid, flights[fid].flight_number, inv.booking_limit, inv.booked_count
            )

    booking = Booking(
        passenger_id=passenger_id,
        status=BookingStatus.CONFIRMED,
        idempotency_key=idempotency_key,
    )

    for index, leg in enumerate(legs, start=1):
        inventories[leg.flight_id].booked_count += 1
        booking.legs.append(
            BookingLeg(
                flight_id=leg.flight_id,
                sequence=index,
                fare_class=leg.fare_class,
                status=LegStatus.CONFIRMED,
            )
        )

    session.add(booking)
    session.flush()
    return booking