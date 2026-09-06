import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import FlightInventory
from app.repositories.inventory import lock_inventories
from app.services.exceptions import FlightNotFound, InvalidOverbookingFactor


def set_overbooking_factor(
    session: Session, flight_id: uuid.UUID, factor: Decimal | float
) -> FlightInventory:
    """
    Change a flight's overbooking factor and recompute its booking limit.

    Takes the same row lock as a booking, so the change serialises against
    in-flight booking transactions rather than racing them.

    Existing confirmed bookings are never cancelled. If the new limit falls
    below the seats already sold, the flight is simply oversold and resolves
    at departure through bump handling.
    """
    factor = Decimal(str(factor))
    if factor < 0:
        raise InvalidOverbookingFactor("Overbooking factor must be non-negative")

    inventories = lock_inventories(session, [flight_id])
    inv = inventories.get(flight_id)
    if inv is None:
        raise FlightNotFound(flight_id)

    inv.overbooking_factor = factor
    inv.booking_limit = FlightInventory.compute_booking_limit(
        inv.physical_capacity, factor
    )
    inv.version += 1

    session.flush()
    return inv