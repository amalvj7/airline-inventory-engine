from sqlalchemy import select

from app.models import Flight, FlightInventory

HEADER = f"{'FLIGHT':<8} {'ROUTE':<10} {'CAP':>4} {'FACTOR':>7} {'LIMIT':>6} {'BOOKED':>7} {'FREE':>5}"
RULE = "-" * len(HEADER)


def flight_rows(session, numbers=None):
    stmt = select(Flight, FlightInventory).join(
        FlightInventory, FlightInventory.flight_id == Flight.id
    )
    if numbers:
        stmt = stmt.where(Flight.flight_number.in_(numbers))
    return session.execute(stmt.order_by(Flight.flight_number)).all()


def print_flights(session, numbers=None, title=None):
    if title:
        print(f"\n{title}")
    print(HEADER)
    print(RULE)
    for flight, inv in flight_rows(session, numbers):
        route = f"{flight.origin}->{flight.destination}"
        free = inv.booking_limit - inv.booked_count
        print(
            f"{flight.flight_number:<8} {route:<10} {inv.physical_capacity:>4} "
            f"{inv.overbooking_factor:>7.2f} {inv.booking_limit:>6} "
            f"{inv.booked_count:>7} {free:>5}"
        )


def banner(text):
    print(f"\n{'=' * 70}\n{text}\n{'=' * 70}")