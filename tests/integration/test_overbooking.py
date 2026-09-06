import pytest

from app.models import FlightInventory
from app.services.booking import LegRequest, create_booking
from app.services.exceptions import InvalidOverbookingFactor, LegUnavailable
from app.services.overbooking import set_overbooking_factor
from app.services.reconciliation import reconcile
from tests.factories import make_flight, make_passenger


def test_raising_the_factor_opens_seats(Session):
    with Session() as s:
        f = make_flight(s, "O1", "AAA", "BBB", capacity=2, factor=0.0)
        ps = [make_passenger(s, f"P{i}") for i in range(3)]
        s.commit()

        create_booking(s, ps[0].id, [LegRequest(f.id)])
        create_booking(s, ps[1].id, [LegRequest(f.id)])
        s.commit()

        with pytest.raises(LegUnavailable):
            create_booking(s, ps[2].id, [LegRequest(f.id)])
        s.rollback()

        set_overbooking_factor(s, f.id, 0.5)   # limit 2 -> 3
        s.commit()

        create_booking(s, ps[2].id, [LegRequest(f.id)])
        s.commit()

        inv = s.get(FlightInventory, f.id)
        assert inv.booking_limit == 3
        assert inv.booked_count == 3
        assert inv.is_oversold          # 3 sold, 2 physical seats


def test_lowering_below_sold_seats_is_legal_and_reconciles(Session):
    with Session() as s:
        f = make_flight(s, "O1", "AAA", "BBB", capacity=4, factor=0.5)  # limit 6
        ps = [make_passenger(s, f"P{i}") for i in range(6)]
        s.commit()

        for p in ps:
            create_booking(s, p.id, [LegRequest(f.id)])
        s.commit()

        set_overbooking_factor(s, f.id, 0.0)   # limit 6 -> 4
        s.commit()

        inv = s.get(FlightInventory, f.id)
        assert inv.booking_limit == 4
        assert inv.booked_count == 6
        assert inv.remaining == -2
        assert not inv.is_available

        report = reconcile(s)
        assert report.ok, "negative remaining is valid state, not drift"


def test_existing_bookings_survive_a_lowered_limit(Session):
    with Session() as s:
        f = make_flight(s, "O1", "AAA", "BBB", capacity=3, factor=1.0)  # limit 6
        ps = [make_passenger(s, f"P{i}") for i in range(5)]
        s.commit()

        for p in ps:
            create_booking(s, p.id, [LegRequest(f.id)])
        s.commit()

        set_overbooking_factor(s, f.id, 0.0)
        s.commit()

        legs = reconcile(s).flights[0]
        assert legs.expected_booked == 5   # nobody was cancelled


def test_negative_factor_is_rejected(Session):
    with Session() as s:
        f = make_flight(s, "O1", "AAA", "BBB", capacity=2)
        s.commit()
        with pytest.raises(InvalidOverbookingFactor):
            set_overbooking_factor(s, f.id, -0.1)


def test_floor_rounding(Session):
    with Session() as s:
        f = make_flight(s, "O1", "AAA", "BBB", capacity=5)
        s.commit()
        inv = set_overbooking_factor(s, f.id, 0.15)   # 5 × 1.15 = 5.75
        s.commit()
        assert inv.booking_limit == 5                 # floor, not 6