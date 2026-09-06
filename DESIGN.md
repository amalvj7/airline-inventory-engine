# Design Document — Airline Multi-Leg Seat Inventory & Overbooking Engine

## 1. Problem Framing

The brief's difficulty is not booking flights. It is that **one physical seat inventory
is shared by many different itineraries**, and that we deliberately sell more seats than
the aircraft has.

Three properties follow from that, and every design decision below exists to protect one
of them:

| Invariant | Meaning |
|---|---|
| **I1 — No inconsistent oversell** | A flight's booked count never exceeds its booking limit, no matter how many bookings race for the last seat. |
| **I2 — Itinerary integrity** | A booking is confirmed on *all* its legs or *none*. No booking is ever left holding a partial itinerary. |
| **I3 — Counter truth** | The stored inventory counter always equals the number of booking legs that actually consume a seat. |

I1 is enforced by pessimistic row locks. I2 by transaction boundaries and an atomic
cancellation policy. I3 is verified, not assumed — see §9, Reconciliation.

---

## 2. Architecture Overview

```text
        Client / Demo Runner
                 |
                 v
  ┌────────────────────────────────┐
  │  API Layer (FastAPI)           │   request validation, HTTP mapping
  │  Pydantic request/response     │
  └───────────────┬────────────────┘
                  v
  ┌────────────────────────────────┐
  │  Service Layer                 │   booking, cancellation, rebooking,
  │  transaction boundaries live   │   overbooking, bump, reconciliation
  │  here — one tx per operation   │
  └───────────────┬────────────────┘
                  v
  ┌────────────────────────────────┐
  │  Repository / SQLAlchemy 2.0   │   row locking (SELECT ... FOR UPDATE)
  └───────────────┬────────────────┘
                  v
         PostgreSQL 18 (READ COMMITTED)
```

**Why this split.** The transaction boundary sits in the service layer, never in the API
layer and never in the repository. That means every inventory mutation has exactly one
place where it begins and commits, which is what makes the concurrency argument
reviewable. Repositories issue locked reads and writes but never commit.

**Why PostgreSQL.** The core requirement is a correct concurrent decrement of a shared
counter. That is a transactional problem, and Postgres gives us `SELECT ... FOR UPDATE`
row locks directly. See §10 for the trade-off against optimistic concurrency.

**Why READ COMMITTED.** The engine keeps Postgres' default isolation level, deliberately.
`SELECT ... FOR UPDATE` blocks a competing transaction until the lock holder commits, and
under READ COMMITTED the blocked statement then re-reads the *newly committed* row and
decides against fresh data. That is exactly what demo scenario (d) shows: three bookings
queued behind an overbooking-factor change wake up and validate against the new limit,
not the one they first saw. Under REPEATABLE READ those same transactions would instead
abort with a serialization failure and every caller would need a retry loop — more
machinery for no extra guarantee, because the lock already serialises the critical
section. The isolation level is doing no work here; the lock is.

**Why FastAPI.** Pydantic models double as the API contract deliverable — request and
response schemas are generated from the same code that validates them, so `/docs` cannot
drift from the implementation.

---

## 3. Data Model

### 3.1 Entities

```text
PASSENGER 1 ──── N BOOKING 1 ──── N BOOKING_LEG N ──── 1 FLIGHT 1 ──── 1 FLIGHT_INVENTORY
```

`BOOKING_LEG` is the junction that makes shared inventory work: many itineraries point at
the same `FLIGHT` row, and therefore compete for the same single `FLIGHT_INVENTORY` row.
That one row is the contention point, and it is exactly what we lock.

### 3.2 Schema

```text
PASSENGER
- id                 UUID PK
- name               text NOT NULL
- tier               text NOT NULL DEFAULT 'STANDARD'   -- PLATINUM|GOLD|STANDARD
- created_at         timestamptz NOT NULL

BOOKING
- id                 UUID PK
- passenger_id       UUID FK -> PASSENGER(id)
- status             text NOT NULL       -- CONFIRMED|CANCELLED|BUMPED_PENDING
- idempotency_key    text UNIQUE NULL    -- safe retries, see §5.4
- created_at         timestamptz NOT NULL

BOOKING_LEG
- id                 UUID PK
- booking_id         UUID FK -> BOOKING(id)
- flight_id          UUID FK -> FLIGHT(id)
- sequence           int NOT NULL        -- 1, 2, 3 ... order within itinerary
- fare_class         text NOT NULL       -- Y|M|B, feeds bump priority
- status             text NOT NULL       -- CONFIRMED|BUMPED|REBOOKED|CANCELLED
- UNIQUE (booking_id, sequence)
- INDEX (flight_id, status)              -- reconciliation + bump queries

FLIGHT
- id                 UUID PK
- flight_number      text NOT NULL
- origin             char(3) NOT NULL
- destination        char(3) NOT NULL
- departure_time     timestamptz NOT NULL
- arrival_time       timestamptz NOT NULL
- status             text NOT NULL       -- SCHEDULED|DEPARTED|CANCELLED

FLIGHT_INVENTORY
- flight_id          UUID PK, FK -> FLIGHT(id)
- physical_capacity  int NOT NULL CHECK (physical_capacity > 0)
- overbooking_factor numeric(4,3) NOT NULL DEFAULT 0 CHECK (overbooking_factor >= 0)
- booking_limit      int NOT NULL        -- derived, see §4.1
- booked_count       int NOT NULL DEFAULT 0 CHECK (booked_count >= 0)
- version            int NOT NULL DEFAULT 0   -- observability only, not for locking
```

### 3.3 One counter, not two

`FLIGHT_INVENTORY` stores **`booked_count`**, and remaining availability is *derived*:

```text
remaining = booking_limit - booked_count
```

This is deliberate. An earlier draft stored `remaining_inventory` directly, which breaks
the moment the overbooking factor changes: recomputing remaining requires knowing how many
seats are already sold, and that number was not stored. Storing `booked_count` means every
operation moves exactly one counter by ±1, and every derived value stays computable from it.

**`remaining` may legitimately be negative.** If capacity is 100, factor 10%, and 108 seats
are sold, lowering the factor to 0% sets the limit to 100 while 108 bookings remain valid —
remaining is −8. We do not cancel existing bookings (§6.2), so this state is reachable by
design. Consequences:

- No `CHECK (remaining >= 0)` constraint may exist.
- The availability test is always `booked_count < booking_limit`, never an equality check.
- Reconciliation treats a negative remaining as **correct**, not as a mismatch.

### 3.4 Which statuses consume inventory

This is the single most important definition in the document, because reconciliation and
every availability check depend on it.

| `BOOKING_LEG.status` | Consumes a seat | Meaning |
|---|:---:|---|
| `CONFIRMED` | **yes** | Normal held seat. |
| `BUMPED` | **yes** | Denied boarding, not yet resolved. Passenger still holds this seat until rebooked or cancelled. |
| `REBOOKED` | no | Reserved for a rebooking audit trail. Not currently written — see §7. |
| `CANCELLED` | no | Released. |

**`BOOKING_LEG.status` is the sole source of truth for inventory.** `BOOKING.status` is a
convenience roll-up for API responses and is never consulted when computing inventory. This
removes the entire class of "booking says cancelled but leg says confirmed" ambiguity.

Holding inventory on `BUMPED` is a deliberate choice: it means a passenger always occupies
exactly one seat somewhere in the system, and the flight is departing anyway, so there is no
one left to sell a released seat to.

---

## 4. Overbooking Policy

### 4.1 Limit derivation

```text
booking_limit = floor(physical_capacity × (1 + overbooking_factor))
```

`floor`, chosen explicitly: 50 seats × 1.15 = 57.5 → **57**. Rounding down never sells a
seat the policy did not authorise. This is asserted in a unit test rather than left to
whichever language rounds which way.

Worked example:

```text
physical_capacity  = 100
overbooking_factor = 0.10
booking_limit      = 110      -- 10 seats may be sold beyond the aircraft
```

The factor is a per-flight column with no global default beyond `0`. There is no hardcoded
buffer anywhere in the codebase — a flight with factor `0` simply never overbooks.

### 4.2 Two limits, two enforcement points

The distinction that makes bumping necessary:

| Number | Value | Enforced |
|---|---|---|
| `booking_limit` | 110 | At **booking time** — how many we will sell. |
| `physical_capacity` | 100 | At **departure** — how many can board. |

The gap between them is the bump population.

### 4.3 Changing the factor mid-flight

`PATCH /flights/{id}/overbooking` runs **inside a transaction that takes the same
`FOR UPDATE` lock on `FLIGHT_INVENTORY`** as a booking does. This is what makes demo
scenario (d) meaningful: the limit change serialises against in-flight booking
transactions, so there is no window where a booking is validated against a stale limit.

The operation recomputes `booking_limit` from the new factor and leaves `booked_count`
untouched. Existing confirmed bookings are never auto-cancelled — an airline does not
revoke a sold ticket because policy changed. If the new limit falls below `booked_count`,
the flight is simply oversold and resolves at departure through bump handling.

---

## 5. Booking Flow

### 5.1 Algorithm

```text
POST /bookings  { passenger_id, legs: [{flight_id, fare_class}, ...] }
        |
        v
  Validate: non-empty, no duplicate flight_id, passenger and flights exist
        |
        v
  BEGIN TRANSACTION
        |
        v
  SELECT * FROM flight_inventory
   WHERE flight_id = ANY(:ids)
   ORDER BY flight_id            <-- deterministic lock order
   FOR UPDATE                    <-- blocks competing bookings
        |
        v
  For every leg:  booked_count < booking_limit ?
        |
   ┌────┴────┐
  all         any
  pass        fail
   |           |
   v           v
 UPDATE      ROLLBACK
 booked_count  → 409 with the
 += 1 per leg    specific full leg
   |
   v
 INSERT booking + booking_legs (CONFIRMED)
   |
   v
 COMMIT → 201
```

### 5.2 Why the lock comes before the check

Every inventory path in this system is **lock → read → decide → write → commit**, never
check-then-lock. A check performed before acquiring the lock is a time-of-check /
time-of-use race: two requests both read `booked_count = 109`, both conclude a seat is
free, both write `110`. Locking first forces the second transaction to block until the
first commits, so it re-reads the *post-commit* value and correctly rejects.

### 5.3 Deadlock avoidance

Multi-leg bookings lock several rows. Two itineraries sharing legs in opposite orders
(A→B and B→A) would deadlock if each locked in itinerary order. All lock acquisition is
therefore sorted by `flight_id` ascending, in a single statement, so no two transactions
can hold locks in conflicting order. Duplicate `flight_id`s in one request are rejected
at validation, which also prevents a request from double-decrementing a single flight.

### 5.4 Idempotency

`POST /bookings` accepts an optional `Idempotency-Key` header stored as a unique column on
`BOOKING`. A retry with the same key returns the original booking rather than consuming a
second seat. Without this, a client timeout on a slow lock wait silently sells two seats.

---

## 6. Cancellation

### 6.1 Policy: itineraries are atomic

**Cancelling any leg of a multi-leg booking cancels the entire booking**, releasing
inventory on every leg it touches, in one transaction.

This directly answers the brief's constraint that cancelling one leg "must not silently
leave the other leg's inventory or the passenger's record in an inconsistent state." The
alternative — leaving orphan legs and reconciling later — creates a state where a passenger
holds a seat on a flight they cannot reach. A confirmed leg from a connection the passenger
can no longer make is not a valid booking; it is inventory withheld from someone who could
use it.

Partial modification of an itinerary is available through **rebooking** (§7), which
*replaces* a leg rather than removing it, so the itinerary is never left with a gap.

```text
POST /bookings/{id}/cancel        (leg_id optional — scope is always the itinerary)
        |
        v
  BEGIN
  Lock all flight_inventory rows for the booking's consuming legs (ORDER BY flight_id)
        |
        v
  UPDATE booking_leg SET status='CANCELLED'
   WHERE booking_id=:id AND status IN ('CONFIRMED','BUMPED')
        |
        v
  Release booked_count -= 1 per row actually updated   <-- see §6.3
        |
        v
  UPDATE booking SET status='CANCELLED'
  COMMIT
```

### 6.2 Cancellation is never triggered by policy changes

Reducing an overbooking factor does not cancel anyone (§4.3). Cancellation happens only on
explicit request or as the resolution of an unresolvable bump.

### 6.3 Double-cancel safety

Inventory release is **conditional on the status transition actually occurring**. The
`UPDATE ... WHERE status IN ('CONFIRMED','BUMPED')` returns a row count, and
`booked_count` is decremented by exactly that count. A second cancel request updates zero
rows and therefore releases zero seats. Without this guard, a retried cancel permanently
corrupts the flight's counter — the counter drifts down and the flight silently oversells
forever.

---

## 7. Rebooking

Rebooking moves one leg from flight X to flight Y while keeping the itinerary intact.

```text
POST /bookings/{id}/rebook  { leg_id, new_flight_id }
        |
        v
  BEGIN
        |
        v
  SELECT ... FOR UPDATE on {old_flight_id, new_flight_id}
   ORDER BY flight_id            <-- BOTH rows, one sorted statement
        |
        v
  new flight: booked_count < booking_limit ?
        |
   ┌────┴────┐
  yes        no
   |          |
   v          v
 old.booked_count -= 1      ROLLBACK → 409
 new.booked_count += 1      (leg stays on original flight,
 leg.flight_id -> new        booking untouched)
 leg.status    -> CONFIRMED
   |
   v
 COMMIT
```

Two details matter. First, **both** inventory rows are locked before the availability check
— an earlier draft checked availability and then locked, which is the TOCTOU race described
in §5.2. Second, the release and the reserve happen in the same transaction, so a failed
rebooking cannot leave the passenger holding zero seats or two.

**The leg row is repointed, not duplicated.** Rebooking updates `BOOKING_LEG.flight_id` in
place rather than closing the old leg and inserting a new one, which keeps `sequence`
stable and the itinerary's shape unchanged. The cost is that the passenger's flight history
is not retained — after a rebooking there is no record of the original flight. The
`REBOOKED` leg status exists in the model for the audit-trail version of this operation and
is currently unused; see Future Improvements in the README.

---

## 8. Bumped Passenger Resolution

### 8.1 What bumping is

Because we deliberately sell up to `booking_limit` (110) but the aircraft seats
`physical_capacity` (100), a full flight can have more confirmed passengers than seats. The
excess passengers are denied boarding — *bumped* — and must be resolved onto other flights.

### 8.2 Selection rule

`POST /flights/{id}/bump` computes `overage = consuming_legs − physical_capacity`. If
`overage <= 0`, it is a no-op. Otherwise it selects exactly `overage` legs by a fully
deterministic ordering:

```sql
ORDER BY passenger.tier_rank DESC,      -- STANDARD(3) bumped before GOLD(2), PLATINUM(1)
         fare_class_rank    DESC,       -- cheapest fare bumped first
         booking.created_at DESC,       -- last booked, first bumped
         booking_leg.id     ASC         -- final tie-break: total ordering guaranteed
```

The last clause exists so the rule is a *total* order. Without it, two identical passengers
make the selection non-deterministic and the demo produces different results on each run,
which is untestable.

The policy is intentionally simple — the brief targets inventory consistency, not
compensation optimisation. It is isolated behind a `BumpPolicy` interface so a different
rule is a single-class change.

### 8.3 Resolution and cascade

A `BUMPED` leg still consumes inventory (§3.4). It resolves one of two ways:

- **Rebooked** onto a later flight with the same origin/destination — inventory moves, the
  itinerary survives.
- **Cancelled** when no alternative exists — and because itineraries are atomic (§6.1),
  **this cascades to the rest of the booking**.

The cascade is the important case. A passenger on A→B→C who is bumped off A→B cannot use
their B→C seat. Holding it would withhold inventory from an itinerary that could actually
fly it. So cancelling the unresolvable bump releases *both* legs, and the downstream seat
returns to the pool for other itineraries. This is the deepest form of the brief's "what
happens to dependent legs" question, and it falls out of the atomicity policy rather than
needing special-case code.

---

## 9. Reconciliation

Because `booked_count` is denormalised, it is verified rather than trusted.

```text
GET /reconciliation   →   per-flight report

expected_booked = COUNT(booking_leg
                        WHERE flight_id = F
                          AND status IN ('CONFIRMED','BUMPED'))

stored_booked   = flight_inventory.booked_count

              expected == stored  →  PASS
              expected != stored  →  MISMATCH (drift, expected, stored)
```

The response also reports `remaining = booking_limit − booked_count` and an `oversold`
flag when `booked_count > physical_capacity`. A negative `remaining` is reported as
**correct** — it is a valid consequence of a lowered overbooking factor, not drift.

This check runs as the final assertion of every concurrency test and closes demo scenario
(e): after races, cancellations, rebookings, bumps and a limit change, the counters still
match the booking records exactly.

---

## 10. Trade-offs

**Pessimistic row locks over optimistic versioning.** `SELECT ... FOR UPDATE` makes the
correctness argument short and reviewable, and contention is genuinely high on a last-seat
race. The cost is that competing bookings block rather than fail fast, and a slow
transaction holding a popular leg stalls others. Optimistic versioning would scale better
under low contention but converts every last-seat race into a retry storm. For a booking
engine where correctness under contention *is* the requirement, blocking is the right
default. The `version` column is present for observability and would be the migration path.

**Denormalised `booked_count` over counting legs on every read.** `COUNT(*)` over
`booking_leg` would be self-evidently correct and impossible to drift, but it makes every
availability check scale with total bookings on the flight and still needs the same lock.
The counter gives O(1) checks; the reconciliation endpoint pays back the risk by making
drift detectable rather than invisible.

**Atomic itinerary cancellation over per-leg cancellation.** Simpler to reason about and
eliminates orphan legs entirely, at the cost of flexibility — a passenger who genuinely
wants to drop only their return leg must rebook instead. Given the brief explicitly calls
out inconsistent dependent legs as the failure mode to avoid, removing the state rather
than managing it is the stronger answer.

**`BUMPED` holds inventory.** Keeps the invariant "one passenger, one seat" and keeps
reconciliation trivially explainable. The cost is that a bumped seat is briefly
unsellable — irrelevant in practice, since the flight is departing.

**Single service over microservices.** One deployable, one database, one transaction
boundary. Distributed inventory would need sagas or a distributed lock and would make the
concurrency demo far harder to prove. Not justified at this scope.

**PostgreSQL specifically, not SQLite.** `SELECT ... FOR UPDATE` is a silent no-op in
SQLite, so the concurrency tests would pass while proving nothing. Postgres is a hard
dependency of the test suite, not a preference.

---

## 11. Test Strategy

38 tests across three layers, all against a real PostgreSQL instance
(`TEST_DATABASE_URL`), truncated between cases.

### 11.1 Layers

| Layer | Location | Exercises | Proves |
|---|---|---|---|
| Integration | `tests/integration/` (23) | service functions on a real session | the domain rules — booking, cancellation, rebooking, overbooking, bump, reconciliation |
| Concurrency | `tests/concurrency/` (2) | real threads, real connections | the locking argument in §5.2 |
| API contract | `tests/api/` (13) | FastAPI `TestClient` | status codes, error envelope, response shape |

**There is no unit layer, deliberately.** Almost every rule in this system is a rule about
a database transaction; a suite built on a mocked session would assert the mock's
behaviour, not Postgres'. The one genuinely pure function, `compute_booking_limit`, is
asserted directly in `test_overbooking.py::test_floor_rounding`. Everything else needs the
database to mean anything.

### 11.2 How the concurrency tests are written

The tests must actually be concurrent, which constrains how they are written:

- **Real parallel connections.** Each thread gets its own engine connection. A shared
  session serialises everything and produces a green suite that proves nothing.
- **`threading.Barrier`** releases all N threads at the same instant, so they contend for
  the same lock rather than arriving in sequence.
- **Assert counts, not absence of error.** `accepted == seats_available` and
  `rejected == N − seats_available` exactly.
- **Classify the rejections.** A rejection must be `LegUnavailable`; any other exception is
  a failure, not a rejection, or a crashing bug reads as correct back-pressure.
- **Verified failure mode.** The last-seat test was confirmed to fail (9 accepts on 1 seat)
  with `FOR UPDATE` removed — see commit `8b639c3`. A concurrency test that has never been
  seen to fail is not evidence.

### 11.3 Requirement coverage

| Brief requirement | Automated test | Demo |
|---|---|---|
| Last-seat race, correct accept/reject counts | `concurrency/test_last_seat.py` | (a) |
| Cross-itinerary shared-leg race, no oversell | `concurrency/test_shared_leg.py` | (b) |
| Cancellation cascading through an itinerary | `integration/test_cancellation.py`, `test_bump.py::test_cancelling_a_bumped_booking_releases_every_leg` | (c) |
| Per-flight overbooking, live limit change | `integration/test_overbooking.py` (5) | (d) |
| Bump resolution at departure | `integration/test_bump.py` (4) | — |
| Reconciliation, including injected drift | `integration/test_reconciliation.py` (3) | (e) |
| Multi-leg atomicity / rollback | `integration/test_booking.py`, `test_rebooking.py` | (b) |
| Retry safety (`Idempotency-Key`) | `api/test_endpoints.py` | — |

### 11.4 Known gaps in the suite

- **The limit-change-under-lock race has no automated test.** It is demonstrated by demo
  scenario (d), which holds the inventory lock open while booking threads queue behind it.
  Promoting it to a test needs the same handshake the demo uses.
- **Concurrent cancel-and-book on the same flight** is untested. The lock ordering makes it
  the same argument as §5.2, but "the same argument" is not evidence.
- **The concurrency tests assert counters directly, not `reconcile()`.** The integration
  suite closes with reconciliation; the race tests assert `booked_count` and `remaining`.
- **Migrations are not exercised by the suite.** Test schema comes from
  `Base.metadata.create_all`, so migration drift would not fail a test. `alembic check`
  covers it and passes.
