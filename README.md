# Airline Multi-Leg Seat Inventory & Overbooking Engine

A booking-inventory service for a simulated route network, where a single physical seat
inventory is shared across overlapping itineraries and overbooking is a tunable per-flight
policy.

The engineering problem is **concurrent, consistent claiming of shared inventory**: many
different itineraries compete for the same physical leg, a multi-leg booking must claim
every leg or none, and the system deliberately sells more seats than the aircraft holds.

Design rationale and trade-offs: [`DESIGN.md`](./DESIGN.md).






---

## Core Guarantees

| | |
|---|---|
| **No inconsistent oversell** | Concurrent bookings for the last seat are serialised by row-level locks. Exactly one succeeds. |
| **All-or-nothing itineraries** | A multi-leg booking claims every leg inside one transaction, or rolls back completely. |
| **Verified counters** | A reconciliation endpoint proves stored inventory matches booking records after any sequence of operations. |

---

## Stack

Python 3.12 · FastAPI · SQLAlchemy 2.0 · PostgreSQL 18 · Alembic · pytest
Dependencies managed with [uv](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`).

**PostgreSQL is a hard requirement, not a preference.** `SELECT ... FOR UPDATE` is a silent
no-op in SQLite, so the concurrency tests would pass without proving anything.

---

## Setup

### Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) — installs Python itself, so no separate Python install is needed
- Docker & Docker Compose (for Postgres), or a local PostgreSQL 15+ instance (developed and tested against 18)
- Git

### Install

```bash
git clone <repository-url>
cd airline-inventory-engine

uv sync                            # creates .venv, installs from uv.lock
```

`uv sync` reads the pinned `uv.lock`, so every environment resolves to identical versions.
There is no `pip install` step and no manual venv activation — `uv run` uses the project
environment automatically.

### Configure

```bash
cp .env.example .env
```

Defaults in `.env.example` match the bundled Compose file, so no edits are needed for local
development:

```dotenv
DATABASE_URL=postgresql+psycopg://airline:airline@localhost:5432/airline
TEST_DATABASE_URL=postgresql+psycopg://airline:airline@localhost:5432/airline_test
LOG_LEVEL=INFO
```

### Database

```bash
docker compose up -d db            # Postgres 18 on :5432
uv run alembic upgrade head        # create schema
uv run python -m app.seed          # load the simulated route network
```

`app.seed` creates a 5-city network (BLR, COK, DEL, BOM, MAA) with connecting flights and
deliberately small capacities, so last-seat races are reachable in a demo without booking
hundreds of rows.

---

## Run

```bash
uv run uvicorn app.main:app --reload --port 8000
```

| | |
|---|---|
| API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| OpenAPI schema | http://localhost:8000/openapi.json |
| Health | http://localhost:8000/health |

### Tests

```bash
uv run pytest                      # full suite
uv run pytest -m concurrency -v    # race tests only
uv run pytest --cov=app --cov-report=term-missing
```

38 tests in three layers — 23 integration, 13 API contract, 2 concurrency. All run against
a real PostgreSQL instance (`TEST_DATABASE_URL`), truncated between cases; the concurrency
suite spawns real threads on independent connections. Full strategy, requirement coverage
and known gaps: [`DESIGN.md`](./DESIGN.md) §11.

### Demo

```bash
uv run python -m demo.run              # all five scenarios, sequentially
uv run python -m demo.run --scenario a # a single scenario
```

Each scenario prints the flight state before, the operations performed, and the state
after; scenario (e) then reconciles every flight in the database against its booking
records. **The demo truncates and re-seeds the dev database on each run.**

Scenarios (a)–(d) run in sequence against the same data so that (e) reconciles across all
of them, which is what the brief asks for. Every scenario checks its own expected
accept/reject counts and final state, and the runner exits non-zero if any of them fail —
so `python -m demo.run` doubles as an end-to-end acceptance check.

---

## API

Full request/response schemas are generated from the Pydantic models and served at `/docs`.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/flights` | Create a flight with capacity and overbooking factor |
| `GET` | `/flights/{flight_id}` | Flight details with live inventory |
| `GET` | `/flights` | List every flight with live inventory |
| `PATCH` | `/flights/{flight_id}/overbooking` | Change the overbooking factor (takes the inventory lock) |
| `POST` | `/passengers` | Create a passenger |
| `POST` | `/bookings` | Book a single- or multi-leg itinerary |
| `GET` | `/bookings/{booking_id}` | Booking with all legs and statuses |
| `POST` | `/bookings/{booking_id}/cancel` | Cancel the itinerary and release all legs |
| `POST` | `/bookings/{booking_id}/rebook` | Move one leg to a different flight |
| `POST` | `/flights/{flight_id}/bump` | Resolve an oversold flight at departure |
| `GET` | `/reconciliation` | Verify inventory against booking records |
| `GET` | `/health` | Liveness plus a database round-trip |

### Example — multi-leg booking

```http
POST /bookings
Idempotency-Key: 4c1f...            # optional; retry-safe
Content-Type: application/json

{
  "passenger_id": "b3f1...",
  "legs": [
    { "flight_id": "a1b2...", "fare_class": "Y" },
    { "flight_id": "c3d4...", "fare_class": "Y" }
  ]
}
```

`fare_class` is optional and defaults to `M`. Legs are numbered by their position in the
request, so the order you send is the order the itinerary flies.

```json
201 Created
{
  "id": "9e8d...",
  "passenger_id": "b3f1...",
  "status": "CONFIRMED",
  "created_at": "2026-09-07T09:14:22.481Z",
  "legs": [
    { "id": "...", "flight_id": "a1b2...", "sequence": 1,
      "fare_class": "Y", "status": "CONFIRMED" },
    { "id": "...", "flight_id": "c3d4...", "sequence": 2,
      "fare_class": "Y", "status": "CONFIRMED" }
  ]
}
```

Rejection names the specific leg that failed, so the client knows which flight to change:

```json
409 Conflict
{
  "error": "LEG_UNAVAILABLE",
  "detail": "No inventory on flight AI205 (60/60)",
  "flight_id": "c3d4...",
  "flight_number": "AI205",
  "booking_limit": 60,
  "booked_count": 60
}
```

### Status codes

| Code | Meaning |
|---|---|
| `201` | Booking, flight, or passenger created |
| `200` | Read, cancel, rebook, bump, reconciliation, health |
| `400` | Domain validation — duplicate `flight_id` in one itinerary, rebooking a leg onto the flight it is already on, `arrival_time` before `departure_time` |
| `404` | Unknown flight, booking, leg, or passenger |
| `409` | No inventory on a required leg (`LEG_UNAVAILABLE`) |
| `422` | Schema validation — empty `legs`, negative `overbooking_factor`, malformed UUID |

Cancellation is idempotent: cancelling an already-cancelled booking returns `200` and
releases nothing, rather than erroring. See `DESIGN.md` §6.3 for why that matters to the
counter.

Domain errors carry the envelope `{"error": "<CODE>", "detail": "<message>"}`, with
`LEG_UNAVAILABLE` adding the flight and counter fields shown above. Two path-lookup 404s
(`GET /flights/{id}`, `GET /bookings/{id}`) still return FastAPI's bare `{"detail": ...}`;
unifying them is listed under Future Improvements.

---

## Key Assumptions

1. **One booking = one passenger = one seat per leg.** Group bookings are not modelled; a
   party of four is four bookings. This keeps the counter arithmetic ±1 and does not change
   the concurrency problem.
2. **`BOOKING_LEG.status` is the sole source of truth for inventory.** `BOOKING.status` is a
   roll-up for display and never influences a counter. `CONFIRMED` and `BUMPED` legs consume
   a seat; `CANCELLED` and `REBOOKED` do not.
3. **Itineraries are atomic.** Cancelling any leg of a multi-leg booking cancels the whole
   booking and releases every leg. Partial changes go through rebooking, which replaces a
   leg rather than removing it.
4. **`booking_limit = floor(physical_capacity × (1 + overbooking_factor))`.** Floor is
   explicit and asserted in tests — rounding down never sells an unauthorised seat.
5. **Remaining inventory may be negative.** Lowering an overbooking factor below the number
   of seats already sold is legal and produces a negative remaining. This is correct state,
   not drift, and reconciliation reports it as `PASS`.
6. **Reducing the overbooking limit never auto-cancels existing bookings.** Sold is sold.
   The flight becomes oversold and resolves at departure through bump handling.
7. **A `BUMPED` leg continues to hold inventory** until it is rebooked or cancelled, so a
   passenger always holds exactly one seat somewhere.
8. **Bump selection is a total ordering** (tier → fare class → booking recency → leg id), so
   results are reproducible across runs.
9. **Departure is triggered manually** via `POST /flights/{id}/bump`. There is no scheduler;
   the demo controls when a flight "departs".
10. **Single-instance deployment.** Correctness relies on Postgres row locks within one
    database. No distributed locking is implemented or needed at this scope.

---

## Scope Limits

Left out deliberately, with reasons:

| Excluded | Why |
|---|---|
| Real GDS / airline integration | Explicitly out of scope in the brief. A simulated schedule exercises the same inventory model. |
| Payments and ticketing | Orthogonal to inventory consistency. Adds a second transactional system without testing anything the brief asks about. |
| Fare pricing, revenue management, yield optimisation | The brief directs focus to the shared-inventory model, not pricing sophistication. `fare_class` exists only to give bump priority a deterministic key. |
| Seat maps and seat assignment | The constraint is *how many* seats are claimable, not which physical seat. A seat map would add UI surface and no concurrency insight. |
| Authentication and authorisation | No multi-tenant or user-identity requirement in the brief. Endpoints are open for demo clarity. |
| Compensation and rebooking-cost optimisation | Real bump economics are a research problem. A simple deterministic priority rule is testable and sufficient. |
| Automatic departure scheduling | A background scheduler makes demos non-deterministic. Manual triggering makes every scenario reproducible. |
| Distributed deployment / horizontal scaling | Would require distributed locks or sagas and would obscure the transactional correctness the brief is actually testing. |

---

## Demo Scenarios

| | Scenario | Proves |
|---|---|---|
| **a** | **Last-seat race** — N threads, one remaining seat, released simultaneously | Exactly 1 accept, N−1 rejects; `booked_count == booking_limit` |
| **b** | **Shared-leg race** — COK→BLR→DEL and MAA→BLR→DEL contend for the last seat on the shared BLR→DEL leg | No oversell across itineraries; the loser holds nothing, not even its own uncontested feeder leg |
| **c** | **Cascading cancellation** — cancel one leg of a 3-leg itinerary | All legs `CANCELLED`, inventory released on every flight, final state printed |
| **d** | **Live limit change** — the factor is lowered while three booking threads are blocked on that flight's inventory lock | Blocked bookings re-read the *new* limit after the change commits, not the one they arrived with: 2 accept, 1 rejects |
| **e** | **Reconciliation** — run after (a)–(d) | Stored `booked_count` matches counted consuming legs on every flight |

Existing bookings surviving a lowered limit, and `remaining` going negative, are covered by
`tests/integration/test_overbooking.py` rather than the demo — they are assertions about
state, and the demo scenario is about the race.

---

## Project Structure

```text
airline-inventory-engine/
├── app/
│   ├── api/              # FastAPI routers, HTTP concerns only
│   ├── schemas/          # Pydantic request/response contracts
│   ├── services/         # transaction boundaries: booking, cancel, rebook, bump, reconcile
│   ├── repositories/     # locked reads and writes; never commits
│   ├── models/           # SQLAlchemy ORM models
│   ├── policies/         # BumpPolicy — swappable bump-selection rule
│   ├── config.py         # pydantic-settings, .env
│   ├── database.py
│   ├── seed.py           # the simulated route network
│   └── main.py
├── demo/
│   ├── run.py            # scenarios a–e, self-verifying
│   ├── concurrency.py    # barrier-released threads on independent sessions
│   └── printing.py       # flight-state tables
├── tests/
│   ├── integration/      # domain rules on a real session
│   ├── api/              # HTTP contract via TestClient
│   └── concurrency/      # threaded races on real connections
├── migrations/           # Alembic
├── scripts/              # test-database bootstrap for Compose
├── docker-compose.yml
├── .env.example
├── pyproject.toml        # dependencies and pytest config
├── uv.lock               # pinned resolution, committed
├── README.md
└── DESIGN.md
```

---

## Future Improvements

What is genuinely incomplete or fragile in what was built. Deliberate exclusions are listed
separately under Scope Limits above; these are the things I would actually fix.

**Incomplete**

- **Bump resolution stops at selection.** `POST /flights/{id}/bump` marks the right
  passengers `BUMPED` and cascades their booking to `BUMPED_PENDING`, but resolving them
  onto another flight is a manual `rebook` call per passenger. Automatic search for the
  next viable flight on the same route is the obvious next step, and the deterministic
  selection policy already gives it a stable input.
- **Rebooking keeps no history.** The leg row is repointed to the new flight
  (`DESIGN.md` §7), so after a rebooking there is no record of the original. The
  `REBOOKED` leg status exists in the model for the close-and-insert version of this
  operation and is currently unused.
- **Flight lifecycle is not enforced.** `FlightStatus` is stored but never set or checked:
  nothing marks a flight `DEPARTED`, and nothing stops a booking on a flight whose
  passengers have already been bumped. Departure is whatever moment you call the bump
  endpoint.
- **Reconciliation detects drift but does not repair it.** A `--repair` mode that corrects
  `booked_count` from the leg count under the row lock is a small addition; leaving it
  read-only was a deliberate first step, not a finished answer.

**Fragile**

- **The `Idempotency-Key` check is not itself concurrency-safe.** Two simultaneous retries
  with the same key both miss the lookup in `create_booking`, and the second `INSERT`
  violates the unique constraint — surfacing as an unhandled `500` instead of returning the
  original booking. The unique constraint means no seat is double-sold — the losing
  transaction rolls back its increment with it — but the caller gets an error it cannot
  interpret for a booking that may well have succeeded. Catching `IntegrityError`,
  re-selecting, and returning the existing row closes it. Sequential retries, the common
  case, work correctly today.
- **Two error-response shapes.** Domain exceptions return
  `{"error": ..., "detail": ...}`; the two path-lookup 404s raised as `HTTPException`
  return bare `{"detail": ...}`. Raising the domain exceptions there instead makes the
  contract uniform.
- **Lock contention is unbounded.** A hot flight serialises every booking that touches it,
  and there is no `statement_timeout` and no client-visible retry hint, so a slow
  transaction degrades into silent waiting rather than a fast, explicit failure.
- **Test coverage gaps** — the limit-change race and concurrent cancel-and-book are
  demonstrated but not asserted automatically. Enumerated in `DESIGN.md` §11.4.

**Deferred**

- **Optimistic concurrency** as an alternative path for low-contention flights, using the
  `version` column that is currently observability-only. Pessimistic locking is right for
  last-seat contention and wrong for a half-empty flight; a policy that picks per flight is
  the interesting version of this system.
- **Group bookings.** One booking is one passenger and one seat per leg, so a party of four
  is four bookings that can partially fail. Real group inventory is an all-or-nothing claim
  of N seats — a different concurrency problem, not a bigger one.

**What I would do first, given another day:** the idempotency race, because it turns a
retry — the exact thing the key exists to make safe — into a `500` the client cannot
interpret; then automatic bump rebooking, because the bump path is the one requirement that
currently ends with a human; then the two missing concurrency tests, because right now the
demo is the only thing proving that behaviour.
