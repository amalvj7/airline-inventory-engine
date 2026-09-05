import pytest

from app.models import FlightInventory
from app.services.booking import LegRequest, create_booking
from app.services.exceptions import InvalidItinerary, LegUnavailable
from tests.factories import make_flight, make_passenger


def test_single_leg_booking_claims_one_seat(Session):
    with Session() as s:
        f = make_flight(s, "T1", "AAA", "BBB", capacity=2)
        p = make_passenger(s)
        s.commit()

        booking = create_booking(s, p.id, [LegRequest(f.id)])
        s.commit()

        inv = s.get(FlightInventory, f.id)
        assert inv.booked_count == 1
        assert inv.remaining == 1
        assert len(booking.legs) == 1


def test_multi_leg_booking_claims_every_leg(Session):
    with Session() as s:
        f1 = make_flight(s, "T1", "AAA", "BBB", capacity=2, hour=0)
        f2 = make_flight(s, "T2", "BBB", "CCC", capacity=2, hour=3)
        p = make_passenger(s)
        s.commit()

        booking = create_booking(s, p.id, [LegRequest(f1.id), LegRequest(f2.id)])
        s.commit()

        assert s.get(FlightInventory, f1.id).booked_count == 1
        assert s.get(FlightInventory, f2.id).booked_count == 1
        assert [leg.sequence for leg in booking.legs] == [1, 2]


def test_full_leg_rolls_back_the_whole_itinerary(Session):
    """The critical atomicity test: leg 2 is full, so leg 1 must not be charged."""
    with Session() as s:
        f1 = make_flight(s, "T1", "AAA", "BBB", capacity=5, hour=0)
        f2 = make_flight(s, "T2", "BBB", "CCC", capacity=1, hour=3)
        p = make_passenger(s)
        other = make_passenger(s, "Blocker")
        s.commit()

        create_booking(s, other.id, [LegRequest(f2.id)])  # fills T2
        s.commit()

        with pytest.raises(LegUnavailable) as exc:
            create_booking(s, p.id, [LegRequest(f1.id), LegRequest(f2.id)])
        s.rollback()

        assert exc.value.flight_number == "T2"
        assert s.get(FlightInventory, f1.id).booked_count == 0  # not charged
        assert s.get(FlightInventory, f2.id).booked_count == 1


def test_duplicate_flight_in_itinerary_is_rejected(Session):
    with Session() as s:
        f = make_flight(s, "T1", "AAA", "BBB", capacity=5)
        p = make_passenger(s)
        s.commit()

        with pytest.raises(InvalidItinerary):
            create_booking(s, p.id, [LegRequest(f.id), LegRequest(f.id)])