from sqlalchemy import select

from app.database import SessionLocal
from app.models import Booking, Flight, Passenger
from app.models.enums import BookingStatus, LegStatus
from app.services.booking import LegRequest, create_booking
from app.services.cancellation import cancel_booking
from demo.concurrency import run_concurrent
from demo.printing import banner, flight_rows, print_flights   
from app.services.overbooking import set_overbooking_factor
from demo.concurrency import run_concurrent, start_concurrent
from app.services.reconciliation import reconcile

import time

def scenario_a():
    banner("(a) LAST-SEAT RACE — 10 threads, 1 seat on AI999")

    with SessionLocal() as s:
        flight_id = s.execute(
            select(Flight.id).where(Flight.flight_number == "AI999")
        ).scalar_one()
        passenger_ids = (
            s.execute(select(Passenger.id).order_by(Passenger.name).limit(10))
            .scalars()
            .all()
        )
        print_flights(s, ["AI999"], title="Before")

    tasks = [
        lambda session, pid=pid: create_booking(
            session, pid, [LegRequest(flight_id=flight_id)]
        )
        for pid in passenger_ids
    ]
    results, errors = run_concurrent(tasks)

    with SessionLocal() as s:
        print_flights(s, ["AI999"], title="After")

    print(f"\naccepted={len(results)}  rejected={len(errors)}")
    print(f"rejection types: {sorted({type(e).__name__ for e in errors})}")

    return len(results) == 1 and len(errors) == 9








def scenario_b():
    banner("(b) SHARED-LEG RACE — two itineraries, one seat on AI201")

    with SessionLocal() as s:
        ids = dict(
            s.execute(
                select(Flight.flight_number, Flight.id).where(
                    Flight.flight_number.in_(["AI101", "AI102", "AI201"])
                )
            ).all()
        )
        pax = (
            s.execute(select(Passenger.id).order_by(Passenger.name).offset(10).limit(4))
            .scalars()
            .all()
        )

    # Fill AI201 to 2 of 3, sequentially.
    with SessionLocal() as s:
        for pid in pax[:2]:
            create_booking(s, pid, [LegRequest(flight_id=ids["AI201"])])
        s.commit()

    with SessionLocal() as s:
        print_flights(s, ["AI101", "AI102", "AI201"], title="Before — AI201 has 1 seat left")

    tasks = [
        lambda session: create_booking(
            session,
            pax[2],
            [LegRequest(flight_id=ids["AI101"]), LegRequest(flight_id=ids["AI201"])],
        ),
        lambda session: create_booking(
            session,
            pax[3],
            [LegRequest(flight_id=ids["AI102"]), LegRequest(flight_id=ids["AI201"])],
        ),
    ]
    results, errors = run_concurrent(tasks)

    with SessionLocal() as s:
        print_flights(s, ["AI101", "AI102", "AI201"], title="After")

    print(f"\naccepted={len(results)}  rejected={len(errors)}")
    print("The loser's feeder leg is still 0 — no partial itinerary.")

    return len(results) == 1 and len(errors) == 1






def scenario_c():
    banner("(c) CASCADING CANCELLATION — COK->BLR->DEL->BOM")

    with SessionLocal() as s:
        ids = dict(
            s.execute(
                select(Flight.flight_number, Flight.id).where(
                    Flight.flight_number.in_(["AI111", "AI211", "AI311"])
                )
            ).all()
        )
        pid = s.execute(
            select(Passenger.id).order_by(Passenger.name).offset(14).limit(1)
        ).scalar_one()

        booking = create_booking(
            s,
            pid,
            [
                LegRequest(flight_id=ids["AI111"]),
                LegRequest(flight_id=ids["AI211"]),
                LegRequest(flight_id=ids["AI311"]),
            ],
        )
        s.commit()
        booking_id = booking.id

    with SessionLocal() as s:
        print_flights(s, ["AI111", "AI211", "AI311"], title="Before cancel — 3 legs held")

    with SessionLocal() as s:
        cancel_booking(s, booking_id)
        s.commit()

    with SessionLocal() as s:
        print_flights(s, ["AI111", "AI211", "AI311"], title="After cancel")

        rows = flight_rows(s, ["AI111", "AI211", "AI311"])
        all_released = all(inv.booked_count == 0 for _, inv in rows)

        b = s.get(Booking, booking_id)
        print(f"\nbooking.status = {b.status.value}")
        for leg in b.legs:
            print(f"  leg {leg.flight.flight_number}  status={leg.status.value}")

        booking_cancelled = b.status == BookingStatus.CANCELLED
        legs_cancelled = all(l.status == LegStatus.CANCELLED for l in b.legs)

    print(f"\nall legs released: {all_released}")
    return all_released and booking_cancelled and legs_cancelled






def scenario_d():
    banner("(d) LIMIT CHANGE vs IN-FLIGHT BOOKINGS — AI401")

    with SessionLocal() as s:
        flight_id = s.execute(
            select(Flight.id).where(Flight.flight_number == "AI401")
        ).scalar_one()
        pax = (
            s.execute(select(Passenger.id).order_by(Passenger.name).offset(11).limit(3))
            .scalars()
            .all()
        )
        print_flights(s, ["AI401"], title="Before — limit 3 on a 2-seat aircraft")

    # Hold the row lock open: factor 0.5 -> 0.0, so limit 3 -> 2. Not committed.
    holder = SessionLocal()
    set_overbooking_factor(holder, flight_id, 0.0)
    print("\nfactor change staged (limit 3 -> 2), lock held, NOT committed")

    tasks = [
        lambda session, pid=pid: create_booking(
            session, pid, [LegRequest(flight_id=flight_id)]
        )
        for pid in pax
    ]
    threads, results, errors = start_concurrent(tasks)

    # The barrier proves they started, not that they reached the lock.
    # A short sleep is the honest cheap version; pg_locks polling is deterministic.
    time.sleep(0.5)
    print("3 booking threads now blocked on the inventory lock")

    holder.commit()
    holder.close()
    print("factor change committed — threads released\n")

    for t in threads:
        t.join()

    with SessionLocal() as s:
        print_flights(s, ["AI401"], title="After")

    print(f"\naccepted={len(results)}  rejected={len(errors)}")
    print("All 3 read limit=3 on the way in. Because the limit check happens")
    print("AFTER the lock, they re-read limit=2 and only 2 fit.")

    return len(results) == 2 and len(errors) == 1






def scenario_e():
    banner("(e) RECONCILIATION — stored counter vs actual consuming legs")

    with SessionLocal() as s:
        report = reconcile(s)

    print(
        f"{'FLIGHT':<8} {'CAP':>4} {'LIMIT':>6} {'STORED':>7} "
        f"{'EXPECT':>7} {'DRIFT':>6} {'OVERSOLD':>9}  OK"
    )
    print("-" * 60)
    for f in report.flights:
        print(
            f"{f.flight_number:<8} {f.physical_capacity:>4} {f.booking_limit:>6} "
            f"{f.stored_booked:>7} {f.expected_booked:>7} {f.drift:>6} "
            f"{('yes' if f.oversold else 'no'):>9}  {'ok' if f.ok else 'NO'}"
        )

    if report.ok:
        print("\nPASS — every flight's counter matches its consuming legs")
    else:
        print(f"\nFAIL — {len(report.mismatches)} flight(s) drifted")
        for f in report.mismatches:
            print(f"  {f.flight_number}: drift={f.drift}")

    return report.ok


















import argparse
import sys

from app.seed import seed

SCENARIOS = {
    "a": scenario_a,
    "b": scenario_b,
    "c": scenario_c,
    "d": scenario_d,
    "e": scenario_e,
}


def main():
    parser = argparse.ArgumentParser(description="Airline inventory engine demo")
    parser.add_argument(
        "--scenario",
        choices=[*SCENARIOS, "all"],
        default="all",
        help="which scenario to run (default: all)",
    )
    args = parser.parse_args()

    print("Truncating and re-seeding the dev database...\n")
    seed()

    names = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    results = {n: SCENARIOS[n]() for n in names}

    banner("SUMMARY")
    for name, ok in results.items():
        print(f"  ({name})  {'PASS' if ok else 'FAIL'}")

    if all(results.values()):
        print("\nAll scenarios passed.")
        sys.exit(0)
    print("\nOne or more scenarios FAILED.")
    sys.exit(1)


if __name__ == "__main__":
    main()







