import threading

import pytest

from app.models import FlightInventory
from app.services.booking import LegRequest, create_booking
from app.services.exceptions import LegUnavailable
from tests.factories import make_flight, make_passenger

pytestmark = pytest.mark.concurrency


def _book_itinerary(Session, passenger_id, flight_ids, barrier, results, lock):
    try:
        with Session() as session:
            barrier.wait()
            try:
                create_booking(
                    session, passenger_id, [LegRequest(f) for f in flight_ids]
                )
                session.commit()
                outcome = "accepted"
            except LegUnavailable:
                session.rollback()
                outcome = "rejected"
        with lock:
            results.append((passenger_id, outcome))
    except Exception as exc:  # noqa: BLE001
        with lock:
            results.append((passenger_id, exc))


def test_two_itineraries_race_for_one_shared_leg(Session):
    """
    Two different multi-leg itineraries converge on a single-seat leg.
    Exactly one wins, and the loser holds no inventory on its first leg.
    """
    with Session() as s:
        feeder_a = make_flight(s, "FA", "COK", "BLR", capacity=5, hour=0)
        feeder_b = make_flight(s, "FB", "MAA", "BLR", capacity=5, hour=0)
        shared = make_flight(s, "SHARED", "BLR", "DEL", capacity=1, hour=3)
        pa = make_passenger(s, "Traveller A")
        pb = make_passenger(s, "Traveller B")
        s.commit()
        ids = {
            "a": (pa.id, [feeder_a.id, shared.id]),
            "b": (pb.id, [feeder_b.id, shared.id]),
            "feeder_a": feeder_a.id,
            "feeder_b": feeder_b.id,
            "shared": shared.id,
        }

    barrier = threading.Barrier(2)
    lock = threading.Lock()
    results = []

    threads = [
        threading.Thread(
            target=_book_itinerary,
            args=(Session, pid, legs, barrier, results, lock),
        )
        for pid, legs in (ids["a"], ids["b"])
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    outcomes = [r[1] for r in results]
    assert all(isinstance(o, str) for o in outcomes), f"unexpected error: {outcomes}"
    assert outcomes.count("accepted") == 1
    assert outcomes.count("rejected") == 1

    winner_id = next(pid for pid, outcome in results if outcome == "accepted")

    with Session() as s:
        assert s.get(FlightInventory, ids["shared"]).booked_count == 1

        # The loser must hold nothing — not even on its own uncontested feeder.
        feeder_a_count = s.get(FlightInventory, ids["feeder_a"]).booked_count
        feeder_b_count = s.get(FlightInventory, ids["feeder_b"]).booked_count

        if winner_id == ids["a"][0]:
            assert feeder_a_count == 1
            assert feeder_b_count == 0, "loser was charged for its feeder leg"
        else:
            assert feeder_b_count == 1
            assert feeder_a_count == 0, "loser was charged for its feeder leg"