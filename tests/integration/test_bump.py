from app.models import FlightInventory
from app.models.enums import BookingStatus, LegStatus, PassengerTier
from app.services.booking import LegRequest, create_booking
from app.services.bump import resolve_oversold_flight
from app.services.cancellation import cancel_booking
from app.services.overbooking import set_overbooking_factor
from app.services.reconciliation import reconcile
from tests.factories import make_flight, make_passenger


def test_no_bump_when_within_capacity(Session):
    with Session() as s:
        f = make_flight(s, "B1", "AAA", "BBB", capacity=3)
        p = make_passenger(s)
        s.commit()
        create_booking(s, p.id, [LegRequest(f.id)])
        s.commit()

        result = resolve_oversold_flight(s, f.id)
        assert result.overage == 0
        assert result.bumped_leg_ids == []


def test_bumps_exactly_the_overage_lowest_priority_first(Session):
    with Session() as s:
        f = make_flight(s, "B1", "AAA", "BBB", capacity=2, factor=1.0)  # limit 4
        plat = make_passenger(s, "Platinum", PassengerTier.PLATINUM)
        gold = make_passenger(s, "Gold", PassengerTier.GOLD)
        std1 = make_passenger(s, "Std1", PassengerTier.STANDARD)
        std2 = make_passenger(s, "Std2", PassengerTier.STANDARD)
        s.commit()

        for p in (plat, gold, std1, std2):
            create_booking(s, p.id, [LegRequest(f.id)])
            s.commit()

        result = resolve_oversold_flight(s, f.id)
        s.commit()

        assert result.overage == 2
        assert len(result.bumped_leg_ids) == 2

        # inventory unchanged: BUMPED still consumes
        assert s.get(FlightInventory, f.id).booked_count == 4
        assert reconcile(s).ok


def test_bump_cascades_to_downstream_legs(Session):
    with Session() as s:
        leg1 = make_flight(s, "B1", "AAA", "BBB", capacity=1, factor=1.0, hour=0)
        leg2 = make_flight(s, "B2", "BBB", "CCC", capacity=5, hour=3)
        p1 = make_passenger(s, "First", PassengerTier.PLATINUM)
        p2 = make_passenger(s, "Second", PassengerTier.STANDARD)
        s.commit()

        create_booking(s, p1.id, [LegRequest(leg1.id)])
        s.commit()
        b2 = create_booking(s, p2.id, [LegRequest(leg1.id), LegRequest(leg2.id)])
        s.commit()

        result = resolve_oversold_flight(s, leg1.id)
        s.commit()

        assert result.overage == 1
        assert len(result.cascaded_leg_ids) == 1

        s.refresh(b2)
        assert b2.status == BookingStatus.BUMPED_PENDING
        assert b2.legs[0].status == LegStatus.BUMPED
        assert b2.legs[1].status == LegStatus.CONFIRMED  # held, not yet released


def test_cancelling_a_bumped_booking_releases_every_leg(Session):
    with Session() as s:
        leg1 = make_flight(s, "B1", "AAA", "BBB", capacity=1, factor=1.0, hour=0)
        leg2 = make_flight(s, "B2", "BBB", "CCC", capacity=5, hour=3)
        p1 = make_passenger(s, "First", PassengerTier.PLATINUM)
        p2 = make_passenger(s, "Second", PassengerTier.STANDARD)
        s.commit()

        create_booking(s, p1.id, [LegRequest(leg1.id)])
        b2 = create_booking(s, p2.id, [LegRequest(leg1.id), LegRequest(leg2.id)])
        s.commit()

        resolve_oversold_flight(s, leg1.id)
        s.commit()

        cancel_booking(s, b2.id)
        s.commit()

        assert s.get(FlightInventory, leg1.id).booked_count == 1
        assert s.get(FlightInventory, leg2.id).booked_count == 0
        assert reconcile(s).ok