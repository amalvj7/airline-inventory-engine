from app.models import FlightInventory
from app.services.booking import LegRequest, create_booking
from app.services.cancellation import cancel_booking
from app.services.reconciliation import reconcile
from tests.factories import make_flight, make_passenger


def test_empty_flights_reconcile(Session):
    with Session() as s:
        make_flight(s, "R1", "AAA", "BBB", capacity=3)
        s.commit()
        report = reconcile(s)
        assert report.ok
        assert report.flights[0].stored_booked == 0
        assert report.flights[0].expected_booked == 0


def test_reconciles_after_bookings_and_cancellations(Session):
    with Session() as s:
        f1 = make_flight(s, "R1", "AAA", "BBB", capacity=5, hour=0)
        f2 = make_flight(s, "R2", "BBB", "CCC", capacity=5, hour=3)
        p1, p2 = make_passenger(s, "One"), make_passenger(s, "Two")
        s.commit()

        b1 = create_booking(s, p1.id, [LegRequest(f1.id), LegRequest(f2.id)])
        create_booking(s, p2.id, [LegRequest(f1.id)])
        s.commit()

        cancel_booking(s, b1.id)
        s.commit()

        report = reconcile(s)
        assert report.ok, report.mismatches
        by_number = {f.flight_number: f for f in report.flights}
        assert by_number["R1"].stored_booked == 1
        assert by_number["R2"].stored_booked == 0


def test_detects_injected_drift(Session):
    """Corrupt the counter directly; reconciliation must catch it."""
    with Session() as s:
        f = make_flight(s, "R1", "AAA", "BBB", capacity=5)
        p = make_passenger(s)
        s.commit()

        create_booking(s, p.id, [LegRequest(f.id)])
        s.commit()

        s.get(FlightInventory, f.id).booked_count = 7   # drift
        s.commit()

        report = reconcile(s)
        assert not report.ok
        mismatch = report.mismatches[0]
        assert mismatch.stored_booked == 7
        assert mismatch.expected_booked == 1
        assert mismatch.drift == 6