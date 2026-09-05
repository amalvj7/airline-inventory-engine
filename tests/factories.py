from datetime import datetime, timedelta, timezone

from app.models import Flight, FlightInventory, Passenger
from app.models.enums import PassengerTier

BASE = datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)


def make_flight(session, number, origin, dest, capacity, factor=0.0, hour=0):
    flight = Flight(
        flight_number=number,
        origin=origin,
        destination=dest,
        departure_time=BASE + timedelta(hours=hour),
        arrival_time=BASE + timedelta(hours=hour + 2),
    )
    flight.inventory = FlightInventory(
        physical_capacity=capacity,
        overbooking_factor=factor,
        booking_limit=FlightInventory.compute_booking_limit(capacity, factor),
        booked_count=0,
    )
    session.add(flight)
    session.flush()
    return flight


def make_passenger(session, name="Test Passenger", tier=PassengerTier.STANDARD):
    p = Passenger(name=name, tier=tier)
    session.add(p)
    session.flush()
    return p