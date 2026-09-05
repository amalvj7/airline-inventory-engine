import uuid

from sqlalchemy.orm import Session

from app.models import BookingLeg, Flight
from app.models.enums import CONSUMING_LEG_STATUSES, BookingStatus, LegStatus
from app.repositories.inventory import lock_inventories
from app.services.exceptions import (
    FlightNotFound,
    InvalidItinerary,
    LegNotFound,
    LegUnavailable,
)


def rebook_leg(
    session: Session,
    booking_id: uuid.UUID,
    leg_id: uuid.UUID,
    new_flight_id: uuid.UUID,
) -> BookingLeg:
    """
    Move one leg of an itinerary onto a different flight.

    Both inventory rows are locked, in sorted order, BEFORE the availability
    check — otherwise the check is stale by the time the seat is claimed.
    Release and reserve happen in one transaction, so a failed rebooking
    leaves the passenger on their original flight rather than on none.
    """
    leg = session.get(BookingLeg, leg_id)
    if leg is None or leg.booking_id != booking_id:
        raise LegNotFound(leg_id)

    if leg.status not in CONSUMING_LEG_STATUSES:
        raise InvalidItinerary("Only a confirmed or bumped leg can be rebooked")

    old_flight_id = leg.flight_id
    if old_flight_id == new_flight_id:
        raise InvalidItinerary("Replacement flight is the current flight")

    if any(
        sibling.flight_id == new_flight_id
        and sibling.id != leg.id
        and sibling.status in CONSUMING_LEG_STATUSES
        for sibling in leg.booking.legs
    ):
        raise InvalidItinerary("Itinerary already uses the replacement flight")

    # Lock BOTH rows, sorted, before deciding anything.
    inventories = lock_inventories(session, [old_flight_id, new_flight_id])

    old_inv = inventories.get(old_flight_id)
    new_inv = inventories.get(new_flight_id)
    if new_inv is None:
        raise FlightNotFound(new_flight_id)

    if not new_inv.is_available:
        new_flight = session.get(Flight, new_flight_id)
        raise LegUnavailable(
            new_flight_id,
            new_flight.flight_number,
            new_inv.booking_limit,
            new_inv.booked_count,
        )

    old_inv.booked_count -= 1
    new_inv.booked_count += 1

    leg.flight_id = new_flight_id
    leg.status = LegStatus.CONFIRMED

    booking = leg.booking
    if all(sib.status == LegStatus.CONFIRMED for sib in booking.legs):
        booking.status = BookingStatus.CONFIRMED

    session.flush()
    return leg