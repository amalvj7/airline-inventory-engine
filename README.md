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

Tests use a separate database (`TEST_DATABASE_URL`) and truncate between cases. The
concurrency suite spawns real threads on independent connections — see `DESIGN.md` §11.

### Demo

```bash
uv run python -m demo.run              # all five scenarios, sequentially
uv run python -m demo.run --scenario a # a single scenario
```

Each scenario prints the pre-state, the operations performed, the post-state, and a
reconciliation result.

---

## API

Full request/response schemas are generated from the Pydantic models and served at `/docs`.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/flights` | Create a flight with capacity and overbooking factor |
| `GET` | `/flights/{flight_id}` | Flight details with live inventory |
| `GET` | `/flights` | List flights, filterable by route and date |
| `PATCH` | `/flights/{flight_id}/overbooking` | Change the overbooking factor (takes the inventory lock) |
| `POST` | `/passengers` | Create a passenger |
| `POST` | `/bookings` | Book a single- or multi-leg itinerary |
| `GET` | `/bookings/{booking_id}` | Booking with all legs and statuses |
| `POST` | `/bookings/{booking_id}/cancel` | Cancel the itinerary and release all legs |
| `POST` | `/bookings/{booking_id}/rebook` | Move one leg to a different flight |
| `POST` | `/flights/{flight_id}/bump` | Resolve an oversold flight at departure |
| `GET` | `/reconciliation` | Verify inventory against booking records |

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

```json
201 Created
{
  "booking_id": "9e8d...",
  "status": "CONFIRMED",
  "legs": [
    { "leg_id": "...", "flight_id": "a1b2...", "sequence": 1,
      "flight_number": "AI101", "status": "CONFIRMED" },
    { "leg_id": "...", "flight_id": "c3d4...", "sequence": 2,
      "flight_number": "AI205", "status": "CONFIRMED" }
  ]
}
```

Rejection names the specific leg that failed, so the client knows which flight to change:

```json
409 Conflict
{
  "error": "LEG_UNAVAILABLE",
  "detail": "No inventory on flight AI205 (c3d4...)",
  "flight_id": "c3d4...",
  "booking_limit": 60,
  "booked_count": 60
}
```

### Status codes

| Code | Meaning |
|---|---|
| `201` | Booking created |
| `200` | Read, cancel, rebook, bump, reconciliation |
| `400` | Malformed request — empty legs, duplicate `flight_id` in one itinerary |
| `404` | Unknown flight, booking, or passenger |
| `409` | No inventory on a required leg, or booking already cancelled |
| `422` | Schema validation failure (FastAPI default) |

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
| **b** | **Shared-leg race** — two different itineraries (A→B→C and X→B) contend for one shared leg | No oversell across itineraries; both counters consistent |
| **c** | **Cascading cancellation** — cancel one leg of a 3-leg itinerary | All legs `CANCELLED`, inventory released on every flight, final state printed |
| **d** | **Live limit change** — lower the overbooking factor while bookings are in flight | New limit applies immediately to pending bookings; existing bookings survive; remaining may go negative |
| **e** | **Reconciliation** — run after (a)–(d) | Stored `booked_count` matches counted consuming legs on every flight |

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
│   ├── policies/         # BumpPolicy, OverbookingPolicy — swappable rules
│   ├── database.py
│   ├── seed.py
│   └── main.py
├── demo/
│   └── run.py            # scenarios a–e
├── tests/
│   ├── unit/
│   ├── integration/
│   └── concurrency/      # threaded races on real connections
├── migrations/           # Alembic
├── docker-compose.yml
├── .env.example
├── pyproject.toml        # dependencies, pytest + ruff config
├── uv.lock               # pinned resolution, committed
├── README.md
└── DESIGN.md
```

---

## Future Improvements

*To be finalised with the submission — current known gaps:*

- **Bump auto-rebooking** is manual; automatic search for the next viable flight on the same
  route is the obvious next step.
- **Reconciliation is read-only.** It detects drift but does not repair it. A `--repair` mode
  that corrects `booked_count` under a lock would be a natural follow-up.
- **No scheduled departure processing** — bumping is triggered by API call.
- **Lock contention is unbounded**; a hot flight serialises all bookings touching it. A
  statement timeout plus a client-visible retry hint would make behaviour under load
  predictable.
- **Optimistic concurrency** as an alternative path for low-contention flights, using the
  existing `version` column.