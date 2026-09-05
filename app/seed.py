from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.database import SessionLocal
from app.models import Flight, FlightInventory, Passenger
from app.models.enums import PassengerTier

BASE = datetime.now(timezone.utc).replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=1)

FLIGHTS = [
    ("AI101", "COK", "BLR", 0, 2, 3, 0.0),
    ("AI102", "MAA", "BLR", 0, 2, 3, 0.0),
    ("AI201", "BLR", "DEL", 3, 6, 2, 0.5),
    ("AI301", "DEL", "BOM", 8, 10, 4, 0.0),
    ("AI999", "BLR", "DEL", 3, 6, 1, 0.0),
]

PASSENGERS = [
    ("Asha Menon", PassengerTier.PLATINUM),
    ("Rahul Nair", PassengerTier.GOLD),
    ("Priya Das", PassengerTier.STANDARD),
    ("Vikram Rao", PassengerTier.STANDARD),
    ("Neha Iyer", PassengerTier.STANDARD),
]


def reset(session) -> None:
    session.execute(
        text(
            "TRUNCATE booking_legs, bookings, flight_inventory, flights, passengers "
            "RESTART IDENTITY CASCADE"
        )
    )


def seed() -> None:
    with SessionLocal() as session:
        reset(session)

        for number, origin, dest, dep_h, arr_h, capacity, factor in FLIGHTS:
            flight = Flight(
                flight_number=number,
                origin=origin,
                destination=dest,
                departure_time=BASE + timedelta(hours=dep_h),
                arrival_time=BASE + timedelta(hours=arr_h),
            )
            flight.inventory = FlightInventory(
                physical_capacity=capacity,
                overbooking_factor=factor,
                booking_limit=FlightInventory.compute_booking_limit(capacity, factor),
                booked_count=0,
            )
            session.add(flight)

        for name, tier in PASSENGERS:
            session.add(Passenger(name=name, tier=tier))

        session.commit()

        print(f"Seeded {len(FLIGHTS)} flights and {len(PASSENGERS)} passengers.")
        for number, o, d, _, _, cap, factor in FLIGHTS:
            limit = FlightInventory.compute_booking_limit(cap, factor)
            print(f"  {number}  {o}->{d}  capacity={cap}  factor={factor}  limit={limit}")


if __name__ == "__main__":
    seed()