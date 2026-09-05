import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking, BookingLeg
from app.models.enums import CONSUMING_LEG_STATUSES, BookingStatus, LegStatus
from app.repositories.inventory import lock_inventories
from app.services.exceptions import BookingNotFound


def cancel_booking(session: Session, booking_id: uuid.UUID) -> Booking:
    """
    Cancel an entire itinerary and release inventory on every consuming leg.

    Itineraries are atomic: there is no partial cancellation. Idempotent —
    cancelling an already-cancelled booking releases nothing.
    """
    booking = session.get(Booking, booking_id)
    if booking is None:
        raise BookingNotFound(booking_id)

    consuming_legs = [leg for leg in booking.legs if leg.status in CONSUMING_LEG_STATUSES]

    if not consuming_legs:
        booking.status = BookingStatus.CANCELLED
        session.flush()
        return booking

    # Lock every affected inventory row before releasing anything.
    inventories = lock_inventories(session, [leg.flight_id for leg in consuming_legs])

    # Re-read leg statuses under the lock: a concurrent cancel may have
    # already released these seats between our read and our lock.
    fresh = session.execute(
        select(BookingLeg)
        .where(BookingLeg.booking_id == booking_id)
        .where(BookingLeg.status.in_(CONSUMING_LEG_STATUSES))
    ).scalars().all()

    for leg in fresh:
        leg.status = LegStatus.CANCELLED
        inventories[leg.flight_id].booked_count -= 1

    booking.status = BookingStatus.CANCELLED
    session.flush()
    return booking