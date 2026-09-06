import pytest

from app.models import FlightInventory
from app.models.enums import BookingStatus, LegStatus, PassengerTier
from app.services.booking import LegRequest, create_booking
from app.services.bump import resolve_oversold_flight
from app.services.exceptions import LegUnavailable
from app.services.reconciliation import reconcile
from app.services.rebooking import rebook_leg
from tests.factories import make_flight, make_passenger


def test_rebooking_moves_inventory_between_flights(Session):
    with Session() as s:
        old = make_flight(s, "R1", "AAA", "BBB", capacity=3, hour=0)
        new = make_flight(s, "R2", "AAA", "BBB", capacity=3, hour=6)
        p = make_passenger(s)
        s.commit()

        booking = create_booking(s, p.id, [LegRequest(old.id)])
        s.commit()

        rebook_leg(s, booking.id, booking.legs[0].id, new.id)
        s.commit()

        assert s.get(FlightInventory, old.id).booked_count == 0
        assert s.get(FlightInventory, new.id).booked_count == 1
        assert reconcile(s).ok


def test_rebooking_onto_a_full_flight_leaves_the_leg_untouched(Session):
    with Session() as s:
        old = make_flight(s, "R1", "AAA", "BBB", capacity=3, hour=0)
        new = make_flight(s, "R2", "AAA", "BBB", capacity=1, hour=6)
        p1, p2 = make_passenger(s, "One"), make_passenger(s, "Two")
        s.commit()

        booking = create_booking(s, p1.id, [LegRequest(old.id)])
        create_booking(s, p2.id, [LegRequest(new.id)])   # fills R2
        s.commit()

        with pytest.raises(LegUnavailable):
            rebook_leg(s, booking.id, booking.legs[0].id, new.id)
        s.rollback()

        assert s.get(FlightInventory, old.id).booked_count == 1  # still there
        assert s.get(FlightInventory, new.id).booked_count == 1
        assert reconcile(s).ok


def test_rebooking_resolves_a_bumped_passenger(Session):
    with Session() as s:
        leg1 = make_flight(s, "R1", "AAA", "BBB", capacity=1, factor=1.0, hour=0)
        alt = make_flight(s, "R1B", "AAA", "BBB", capacity=3, hour=6)
        p1 = make_passenger(s, "Keeps seat", PassengerTier.PLATINUM)
        p2 = make_passenger(s, "Gets bumped", PassengerTier.STANDARD)
        s.commit()

        create_booking(s, p1.id, [LegRequest(leg1.id)])
        b2 = create_booking(s, p2.id, [LegRequest(leg1.id)])
        s.commit()

        resolve_oversold_flight(s, leg1.id)
        s.commit()
        assert b2.legs[0].status == LegStatus.BUMPED

        rebook_leg(s, b2.id, b2.legs[0].id, alt.id)
        s.commit()

        assert b2.legs[0].status == LegStatus.CONFIRMED
        assert b2.status == BookingStatus.CONFIRMED
        assert s.get(FlightInventory, leg1.id).booked_count == 1
        assert s.get(FlightInventory, alt.id).booked_count == 1
        assert reconcile(s).ok


def test_multi_leg_itinerary_survives_rebooking_one_leg(Session):
    with Session() as s:
        f1 = make_flight(s, "R1", "AAA", "BBB", capacity=3, hour=0)
        f2 = make_flight(s, "R2", "BBB", "CCC", capacity=3, hour=3)
        f2_alt = make_flight(s, "R2B", "BBB", "CCC", capacity=3, hour=5)
        p = make_passenger(s)
        s.commit()

        booking = create_booking(s, p.id, [LegRequest(f1.id), LegRequest(f2.id)])
        s.commit()

        rebook_leg(s, booking.id, booking.legs[1].id, f2_alt.id)
        s.commit()

        assert [leg.sequence for leg in booking.legs] == [1, 2]
        assert s.get(FlightInventory, f1.id).booked_count == 1
        assert s.get(FlightInventory, f2.id).booked_count == 0
        assert s.get(FlightInventory, f2_alt.id).booked_count == 1
        assert reconcile(s).ok