"""Server-side concurrency demonstration.

Fires N genuinely simultaneous booking attempts and reports what the engine did.
Same mechanism as `tests/concurrency/` and `demo/run.py` -- real threads, real
connections, released together by one barrier -- exposed over HTTP so a browser
can trigger it. A browser cannot itself produce simultaneous requests with the
precision this needs.

Two shapes:
  * one group of clients all claiming the same flight  -> the last-seat race
  * several groups on different itineraries that share a leg -> the shared-leg
    race, where the loser must hold nothing at all, not even its uncontested legs
"""

import threading
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models import Flight, Passenger
from app.services.booking import LegRequest, create_booking
from app.services.exceptions import FlightNotFound, InvalidItinerary, LegUnavailable

MIN_CLIENTS = 2
MAX_CLIENTS = 20


@dataclass(frozen=True)
class Snapshot:
    booking_limit: int
    booked_count: int
    remaining: int
    is_oversold: bool


@dataclass(frozen=True)
class FlightOutcome:
    flight_id: uuid.UUID
    flight_number: str
    before: Snapshot
    after: Snapshot
    seats_claimed: int


@dataclass(frozen=True)
class GroupOutcome:
    label: str
    flight_numbers: list[str]
    clients: int
    accepted: int
    rejected: int


@dataclass
class RaceResult:
    clients: int
    accepted: int
    rejected: int
    failed: int
    groups: list[GroupOutcome]
    flights: list[FlightOutcome]
    seats_claimed: int
    seats_expected: int
    within_limit: bool
    consistent: bool
    elapsed_ms: int
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RaceGroup:
    """One cohort of clients all attempting the same itinerary."""

    flight_ids: list[uuid.UUID]
    clients: int
    label: str | None = None


def _snapshot(inventory) -> Snapshot:
    return Snapshot(
        booking_limit=inventory.booking_limit,
        booked_count=inventory.booked_count,
        remaining=inventory.remaining,
        is_oversold=inventory.is_oversold,
    )


def run_race(
    session: Session,
    groups: list[RaceGroup],
    session_factory: sessionmaker | None = None,
) -> RaceResult:
    """`session_factory` overrides the dedicated race pool; tests inject their own
    so the threads hit the same database the test set its fixtures up in."""
    if not groups:
        raise InvalidItinerary("At least one group of clients is required")

    total_clients = sum(g.clients for g in groups)
    if not MIN_CLIENTS <= total_clients <= MAX_CLIENTS:
        raise InvalidItinerary(
            f"Total clients must be between {MIN_CLIENTS} and {MAX_CLIENTS}"
        )

    for group in groups:
        if not group.flight_ids:
            raise InvalidItinerary("An itinerary must contain at least one flight")
        if len(set(group.flight_ids)) != len(group.flight_ids):
            raise InvalidItinerary("An itinerary cannot use the same flight twice")

    # every distinct flight any group touches, in a stable order
    flight_ids: list[uuid.UUID] = []
    for group in groups:
        for fid in group.flight_ids:
            if fid not in flight_ids:
                flight_ids.append(fid)

    flights: dict[uuid.UUID, Flight] = {}
    for fid in flight_ids:
        flight = session.get(Flight, fid)
        if flight is None:
            raise FlightNotFound(fid)
        flights[fid] = flight

    numbers = {fid: f.flight_number for fid, f in flights.items()}
    before = {fid: _snapshot(f.inventory) for fid, f in flights.items()}

    passenger_ids = list(
        session.execute(
            select(Passenger.id).order_by(Passenger.name).limit(total_clients)
        )
        .scalars()
        .all()
    )
    if not passenger_ids:
        raise InvalidItinerary("No passengers exist to race with")

    # release the read transaction so the post-race read sees the threads' commits
    session.rollback()

    # A dedicated pool sized to the race. Every client holds a connection for the
    # whole attempt while blocked on the row lock; borrowing from the request pool
    # would starve ordinary traffic, or block here if that pool is smaller.
    engine = None
    if session_factory is None:
        engine = create_engine(
            settings.database_url, pool_size=total_clients, max_overflow=0
        )
        session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    barrier = threading.Barrier(total_clients)
    lock = threading.Lock()
    tally = {i: {"accepted": 0, "rejected": 0} for i in range(len(groups))}
    errors: list[str] = []

    def attempt(group_index: int, passenger_id: uuid.UUID, itinerary: list[uuid.UUID]) -> None:
        try:
            with session_factory() as s:
                barrier.wait()  # every thread released at the same instant
                try:
                    create_booking(s, passenger_id, [LegRequest(f) for f in itinerary])
                    s.commit()
                    with lock:
                        tally[group_index]["accepted"] += 1
                except LegUnavailable:
                    s.rollback()
                    with lock:
                        tally[group_index]["rejected"] += 1
        except Exception as exc:  # noqa: BLE001 -- unexpected; surfaced, not swallowed
            with lock:
                errors.append(f"{type(exc).__name__}: {exc}")

    threads: list[threading.Thread] = []
    client_number = 0
    for index, group in enumerate(groups):
        for _ in range(group.clients):
            passenger_id = passenger_ids[client_number % len(passenger_ids)]
            threads.append(
                threading.Thread(target=attempt, args=(index, passenger_id, group.flight_ids))
            )
            client_number += 1

    started = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if engine is not None:
        engine.dispose()

    flight_outcomes: list[FlightOutcome] = []
    total_claimed = 0
    within_limit = True
    for fid in flight_ids:
        flight = session.get(Flight, fid)
        session.refresh(flight.inventory)
        after = _snapshot(flight.inventory)
        claimed = after.booked_count - before[fid].booked_count
        total_claimed += claimed
        within_limit = within_limit and after.booked_count <= after.booking_limit
        flight_outcomes.append(
            FlightOutcome(
                flight_id=fid,
                flight_number=numbers[fid],
                before=before[fid],
                after=after,
                seats_claimed=claimed,
            )
        )

    group_outcomes = [
        GroupOutcome(
            label=group.label or " → ".join(numbers[f] for f in group.flight_ids),
            flight_numbers=[numbers[f] for f in group.flight_ids],
            clients=group.clients,
            accepted=tally[i]["accepted"],
            rejected=tally[i]["rejected"],
        )
        for i, group in enumerate(groups)
    ]

    # every accepted booking must have claimed exactly one seat on each of its legs
    seats_expected = sum(o.accepted * len(g.flight_ids) for o, g in zip(group_outcomes, groups))

    return RaceResult(
        clients=total_clients,
        accepted=sum(o.accepted for o in group_outcomes),
        rejected=sum(o.rejected for o in group_outcomes),
        failed=len(errors),
        groups=group_outcomes,
        flights=flight_outcomes,
        seats_claimed=total_claimed,
        seats_expected=seats_expected,
        within_limit=within_limit,
        consistent=total_claimed == seats_expected,
        elapsed_ms=elapsed_ms,
        errors=errors,
    )
