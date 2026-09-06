import threading

import pytest

from app.models import FlightInventory
from app.services.booking import LegRequest, create_booking
from app.services.exceptions import LegUnavailable
from tests.factories import make_flight, make_passenger

pytestmark = pytest.mark.concurrency


def _attempt(Session, passenger_id, flight_id, barrier, accepted, rejected, errors, lock):
    """One booking attempt on its own connection and its own transaction."""
    try:
        with Session() as session:
            barrier.wait()  # all threads released at the same instant
            try:
                create_booking(session, passenger_id, [LegRequest(flight_id)])
                session.commit()
                with lock:
                    accepted.append(passenger_id)
            except LegUnavailable:
                session.rollback()
                with lock:
                    rejected.append(passenger_id)
    except Exception as exc:  # noqa: BLE001
        with lock:
            errors.append(exc)


def test_ten_threads_one_seat(Session):
    threads_count = 10

    with Session() as s:
        flight = make_flight(s, "RACE1", "AAA", "BBB", capacity=1)
        passengers = [make_passenger(s, f"P{i}") for i in range(threads_count)]
        s.commit()
        flight_id = flight.id
        passenger_ids = [p.id for p in passengers]

    barrier = threading.Barrier(threads_count)
    lock = threading.Lock()
    accepted, rejected, errors = [], [], []

    threads = [
        threading.Thread(
            target=_attempt,
            args=(Session, pid, flight_id, barrier, accepted, rejected, errors, lock),
        )
        for pid in passenger_ids
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == [], f"unexpected errors: {errors}"
    assert len(accepted) == 1, f"expected exactly 1 accept, got {len(accepted)}"
    assert len(rejected) == threads_count - 1

    with Session() as s:
        inv = s.get(FlightInventory, flight_id)
        assert inv.booked_count == 1
        assert inv.remaining == 0