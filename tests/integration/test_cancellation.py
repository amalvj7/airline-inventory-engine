import pytest

from app.models import FlightInventory
from app.models.enums import BookingStatus, LegStatus
from app.services.booking import LegRequest, create_booking
from app.services.cancellation import cancel_booking
from tests.factories import make_flight, make_passenger


def test_cancel_releases_every_leg(Session):
    with Session() as s:
        f1 = make_flight(s, "C1", "AAA", "BBB", capacity=3, hour=0)
        f2 = make_flight(s, "C2", "BBB", "CCC", capacity=3, hour=3)
        f3 = make_flight(s, "C3", "CCC", "DDD", capacity=3, hour=6)
        p = make_passenger(s)
        s.commit()

        booking = create_booking(
            s, p.id, [LegRequest(f1.id), LegRequest(f2.id), LegRequest(f3.id)]
        )
        s.commit()
        assert all(s.get(FlightInventory, f).booked_count == 1 for f in (f1.id, f2.id, f3.id))

        cancel_booking(s, booking.id)
        s.commit()

        assert booking.status == BookingStatus.CANCELLED
        assert all(leg.status == LegStatus.CANCELLED for leg in booking.legs)
        assert all(s.get(FlightInventory, f).booked_count == 0 for f in (f1.id, f2.id, f3.id))


def test_double_cancel_releases_inventory_once(Session):
    """A retried cancel must not decrement the counter twice."""
    with Session() as s:
        f = make_flight(s, "C1", "AAA", "BBB", capacity=3)
        p1, p2 = make_passenger(s, "One"), make_passenger(s, "Two")
        s.commit()

        b1 = create_booking(s, p1.id, [LegRequest(f.id)])
        create_booking(s, p2.id, [LegRequest(f.id)])
        s.commit()
        assert s.get(FlightInventory, f.id).booked_count == 2

        cancel_booking(s, b1.id)
        s.commit()
        cancel_booking(s, b1.id)   # retry
        s.commit()

        assert s.get(FlightInventory, f.id).booked_count == 1


def test_cancelled_seat_is_immediately_rebookable(Session):
    with Session() as s:
        f = make_flight(s, "C1", "AAA", "BBB", capacity=1)
        p1, p2 = make_passenger(s, "One"), make_passenger(s, "Two")
        s.commit()

        b1 = create_booking(s, p1.id, [LegRequest(f.id)])
        s.commit()

        cancel_booking(s, b1.id)
        s.commit()

        create_booking(s, p2.id, [LegRequest(f.id)])
        s.commit()
        assert s.get(FlightInventory, f.id).booked_count == 1