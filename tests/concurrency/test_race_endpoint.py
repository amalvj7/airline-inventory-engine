import pytest

from app.services.race import RaceGroup, run_race
from tests.factories import make_flight, make_passenger

pytestmark = pytest.mark.concurrency


def _one(flight_id, clients):
    return [RaceGroup(flight_ids=[flight_id], clients=clients)]


def test_race_sells_exactly_the_last_seat(Session):
    """Ten clients, one seat: one wins, nine are rejected, no oversell."""
    with Session() as s:
        flight = make_flight(s, "RACEAPI", "AAA", "BBB", capacity=1)
        for i in range(10):
            make_passenger(s, f"Racer {i}")
        s.commit()
        flight_id = flight.id

    with Session() as s:
        result = run_race(s, _one(flight_id, 10), session_factory=Session)

    assert result.accepted == 1
    assert result.rejected == 9
    assert result.failed == 0, result.errors
    assert result.flights[0].after.booked_count == 1
    assert result.within_limit
    assert result.consistent


def test_race_fills_an_overbooked_flight_to_its_limit(Session):
    """capacity 2, factor 1.0 -> limit 4. Ten clients must claim exactly 4."""
    with Session() as s:
        flight = make_flight(s, "RACEOB", "AAA", "BBB", capacity=2, factor=1.0)
        for i in range(10):
            make_passenger(s, f"Racer {i}")
        s.commit()
        flight_id = flight.id

    with Session() as s:
        result = run_race(s, _one(flight_id, 10), session_factory=Session)

    assert result.flights[0].after.booking_limit == 4
    assert result.accepted == 4
    assert result.rejected == 6
    assert result.within_limit
    assert result.consistent
    # sold past physical capacity on purpose -- that is the overbooking policy
    assert result.flights[0].after.is_oversold


def test_shared_leg_race_admits_one_itinerary_and_frees_the_loser(Session):
    """Scenario (b): two itineraries, one seat on the leg they share.

    The loser must hold nothing at all -- not even its own uncontested feeder
    leg -- because a multi-leg booking is claimed all-or-nothing.
    """
    with Session() as s:
        feeder_x = make_flight(s, "FEEDX", "COK", "BLR", capacity=5, hour=0)
        feeder_y = make_flight(s, "FEEDY", "MAA", "BLR", capacity=5, hour=0)
        shared = make_flight(s, "SHARED", "BLR", "DEL", capacity=1, hour=3)
        for i in range(6):
            make_passenger(s, f"Racer {i}")
        s.commit()
        x, y, shared_id = feeder_x.id, feeder_y.id, shared.id

    with Session() as s:
        result = run_race(
            s,
            [
                RaceGroup(flight_ids=[x, shared_id], clients=3, label="COK→BLR→DEL"),
                RaceGroup(flight_ids=[y, shared_id], clients=3, label="MAA→BLR→DEL"),
            ],
            session_factory=Session,
        )

    assert result.failed == 0, result.errors
    assert result.accepted == 1          # only one seat on the shared leg
    assert result.rejected == 5
    assert result.consistent
    assert result.within_limit

    by_number = {f.flight_number: f for f in result.flights}
    assert by_number["SHARED"].after.booked_count == 1

    # the winner took its own feeder leg; every loser released theirs
    feeders_claimed = by_number["FEEDX"].seats_claimed + by_number["FEEDY"].seats_claimed
    assert feeders_claimed == 1, "a rejected itinerary must not hold its feeder leg"
    assert result.seats_claimed == result.seats_expected == 2  # 1 booking × 2 legs


def test_race_on_a_full_flight_rejects_everyone(Session):
    with Session() as s:
        flight = make_flight(s, "RACEFULL", "AAA", "BBB", capacity=1)
        for i in range(4):
            make_passenger(s, f"Racer {i}")
        s.commit()
        flight_id = flight.id

    with Session() as s:
        run_race(s, _one(flight_id, 2), session_factory=Session)
    with Session() as s:
        second = run_race(s, _one(flight_id, 4), session_factory=Session)

    assert second.accepted == 0
    assert second.rejected == 4
    assert second.seats_claimed == 0
    assert second.consistent
