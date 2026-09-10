# Airline Multi-Leg Seat Inventory & Overbooking Engine

A booking-inventory service for a simulated route network, where a single physical seat
inventory is shared across overlapping itineraries and overbooking is a tunable per-flight
policy.

The engineering problem is **concurrent, consistent claiming of shared inventory**: many
different itineraries compete for the same physical leg, a multi-leg booking must claim
every leg or none, and the system deliberately sells more seats than the aircraft holds.

Design rationale and trade-offs: [`DESIGN.md`](./DESIGN.md).

**Live:** [UI](https://airline-ui-wvyw.onrender.com) ·
[API docs](https://airline-inventory-engine.onrender.com/docs) ·
[health](https://airline-inventory-engine.onrender.com/health)

> Hosted on Render's free tier: the API sleeps after ~15 minutes idle, so the first request
> can take up to a minute. The UI is static and always loads instantly.






---

## Core Guarantees

| | |
|---|---|
| **No inconsistent oversell** | Concurrent bookings for the last seat are serialised by row-level locks. Exactly one succeeds. |
| **All-or-nothing itineraries** | A multi-leg booking claims every leg inside one transaction, or rolls back completely. |
| **Verified counters** | A reconciliation endpoint proves stored inventory matches booking records after any sequence of operations. |

---

## Stack

**Backend** — Python 3.12 · FastAPI · SQLAlchemy 2.0 · PostgreSQL 18 · Alembic · pytest
Dependencies managed with [uv](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`).

**Frontend** — React 19 · Vite 8 · no state library, no component library, no router.
It compiles to three static files (~67 kB gzipped) and talks to the API over JSON.

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
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

`CORS_ORIGINS` is a comma-separated list of browser origins permitted to call the API. The
defaults cover the Vite dev server (`localhost` and `127.0.0.1` are distinct origins to a
browser, so both are listed). Add the deployed frontend origin here at deploy time —
scheme, host and port must match exactly, with no trailing slash. Requests from `curl`,
the test suite and Swagger UI are unaffected: CORS is enforced by browsers, not servers.

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

61 tests — 24 integration, 26 API contract, 6 concurrency, 5 config. All but the config
tests run against a real PostgreSQL instance (`TEST_DATABASE_URL`), truncated between
cases; the concurrency suite spawns real threads on independent connections. Full
strategy, requirement coverage and known gaps: [`DESIGN.md`](./DESIGN.md) §11.

### Frontend

```bash
cd frontend
cp .env.example .env               # VITE_API_URL — the deployed API by default
npm install
npm run dev                        # http://localhost:5173
```

To develop against a local backend instead, set `VITE_API_URL=http://127.0.0.1:8000` and run
uvicorn alongside. Use `127.0.0.1` rather than `localhost`: uvicorn binds IPv4, and a browser
resolving `localhost` to `::1` will fail with an opaque network error.

`VITE_*` variables are substituted into the bundle **at build time**, not read at runtime — a
browser cannot see server environment variables. So the value must be set wherever the build
runs, changing it needs a rebuild rather than a restart, and anything in a `VITE_` variable is
public by definition. Never put a secret there.

If Vite reports *"Port 5173 in use, using 5174"*, stop and free the port. The API's
`CORS_ORIGINS` allows `5173`, so a page served from `5174` is blocked on every request.

```bash
npm run build                      # -> dist/, three static files
```

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
| `GET` | `/passengers` | List passengers (`limit`, `offset`) |
| `POST` | `/bookings` | Book a single- or multi-leg itinerary |
| `GET` | `/bookings` | List bookings, newest first (`passenger_id`, `flight_id`, `limit`, `offset`) |
| `GET` | `/bookings/{booking_id}` | Booking with all legs and statuses |
| `POST` | `/bookings/{booking_id}/cancel` | Cancel the itinerary and release all legs |
| `POST` | `/bookings/{booking_id}/rebook` | Move one leg to a different flight |
| `POST` | `/flights/{flight_id}/bump` | Resolve an oversold flight at departure |
| `GET` | `/reconciliation` | Verify inventory against booking records |
| `POST` | `/demo/race` | Fire N simultaneous booking attempts (see below) |
| `GET` | `/health` | Liveness plus a database round-trip |

### `POST /demo/race`

A concurrency demonstration the browser can trigger. A browser cannot itself issue genuinely
simultaneous requests, so the race runs server-side: real threads on independent connections,
released together by a barrier — the same mechanism as `tests/concurrency/` and `demo/run.py`.

It **writes real bookings**; it does not simulate. Set `DEMO_ENDPOINTS_ENABLED=false` to
return `404` instead.

```jsonc
// last-seat race: N clients, one flight
{ "flight_id": "…", "clients": 10 }

// shared-leg race: two itineraries contending for a leg they share
{ "groups": [
    { "flight_ids": ["…AI101", "…AI999"], "clients": 3, "label": "COK→BLR→DEL" },
    { "flight_ids": ["…AI102", "…AI999"], "clients": 3, "label": "MAA→BLR→DEL" }
]}
```

The response reports per-group accept/reject counts, before/after inventory for every flight
touched, and two invariants: `within_limit` (no flight exceeded its booking limit) and
`consistent` (seats claimed equals accepted bookings × legs). Total clients are capped at 20.

The race opens **its own connection pool**, sized to the client count. Every client holds a
connection while blocked on the row lock, so borrowing from the request pool would either
starve ordinary traffic or deadlock the race against itself.

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

Every failure response carries the same envelope, `{"error": "<CODE>", "detail": "<message>"}`,
with `LEG_UNAVAILABLE` adding the flight and counter fields shown above. There is one error
shape to parse, including on path-lookup 404s.

---

## Deployment

Three Render services from this one repository:

| Service | Type | Notes |
|---|---|---|
| `airline-db` | managed PostgreSQL 18 | migrated and seeded from a laptop over the external URL |
| `airline-inventory-engine` | web service (Python) | root directory blank · `pip install -r requirements.txt` · `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| `airline-ui` | static site | root directory `frontend` · `npm install && npm run build` · publish `dist` |

**Environment variables.** The API needs `DATABASE_URL` (the *internal* URL — it stays on
Render's private network), `CORS_ORIGINS` including the deployed UI origin, and optionally
`DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `LOG_LEVEL` / `DEMO_ENDPOINTS_ENABLED`. The static site
needs `VITE_API_URL` at build time.

**`requirements.txt` is generated, not hand-written.** Render's Python runtime installs with
pip, which cannot read `uv.lock`. Regenerate whenever dependencies change:

```bash
uv export --no-dev --no-emit-project --no-hashes -o requirements.txt
```

**Managed Postgres hands out `postgres://`**, an alias SQLAlchemy 2 removed, and bare
`postgresql://` resolves to psycopg2 rather than psycopg 3. A validator on `Settings`
rewrites both to `postgresql+psycopg://`. Because `migrations/env.py` reads the same
`Settings`, Alembic inherits the fix — nothing in `migrations/` knows about it.

**Schema and seed are applied deliberately, not on boot.** An app that creates its own tables
at startup races itself when several instances start together, and makes schema changes an
invisible side effect of a restart:

```bash
DATABASE_URL='<external url>' uv run alembic upgrade head
DATABASE_URL='<external url>' uv run python -m app.seed   # destructive: truncates first
```

Re-running the seed is also how demo state is reset.

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

### In the browser

`demo/run.py` is the authoritative, self-verifying proof. The UI covers the same ground
interactively, which is a different kind of evidence:

| | In the UI |
|---|---|
| **a** | **Concurrency test → Last seat** — N clients, one flight |
| **b** | **Concurrency test → Shared leg** — two itineraries, one contested leg. The flights table shows the loser's feeder claiming `+0` |
| **c** | Book a multi-leg itinerary, then **Cancel** — every leg releases |
| **d** | **Factor** on any flight — the limit moves, existing bookings do not. The *blocked-thread* half of (d) is script-only |
| **e** | **Reconciliation → Verify counters** |

---

## Project Structure

```text
airline-inventory-engine/
├── app/
│   ├── api/              # FastAPI routers, HTTP concerns only
│   ├── schemas/          # Pydantic request/response contracts
│   ├── services/         # transaction boundaries: booking, cancel, rebook, bump,
│   │                     #   reconcile, race
│   ├── repositories/     # locked reads and writes; never commits
│   ├── models/           # SQLAlchemy ORM models
│   ├── policies/         # BumpPolicy — swappable bump-selection rule
│   ├── config.py         # pydantic-settings, .env
│   ├── database.py
│   ├── seed.py           # the simulated route network
│   └── main.py
├── frontend/             # React + Vite single-page UI
│   ├── src/
│   │   ├── api.js        # one fetch wrapper; one ApiError for every endpoint
│   │   ├── App.jsx       # owns all state, one shared refresh
│   │   └── components/   # Race, Flights, BookSeat, Bookings, Passengers, Ops
│   └── .env.example      # VITE_API_URL
├── demo/
│   ├── run.py            # scenarios a–e, self-verifying
│   ├── concurrency.py    # barrier-released threads on independent sessions
│   └── printing.py       # flight-state tables
├── tests/
│   ├── integration/      # domain rules on a real session
│   ├── api/              # HTTP contract via TestClient
│   ├── concurrency/      # threaded races on real connections
│   └── test_config.py    # settings parsing; the only pure-logic tests
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
- **Lock contention is unbounded.** A hot flight serialises every booking that touches it,
  and there is no `statement_timeout` and no client-visible retry hint, so a slow
  transaction degrades into silent waiting rather than a fast, explicit failure.
- **Test coverage gaps** — the limit-change race and concurrent cancel-and-book are
  demonstrated but not asserted automatically. Enumerated in `DESIGN.md` §11.4.

- **`POST /demo/race` writes to whatever database it is pointed at.** It is a demonstration,
  not a sandbox: on the deployed instance it creates real bookings that persist until the
  seed is re-run. It is capped at 20 clients and can be switched off entirely, but a stricter
  version would run inside a transaction that always rolls back — which would then prove
  rather less, since the commits are the point.

- **No Dockerfile.** The API deploys via Render's native Python runtime, so the build depends
  on that platform's runtime detection rather than something reproducible anywhere. A
  Dockerfile is the obvious next step; it was skipped under time pressure, not on principle.

- **The frontend has no polling or optimistic updates.** Two people using it simultaneously
  each need to refresh to see the other's bookings. Deliberate for a demonstration — the
  server's answer is the point, so the UI always waits for it — but a real client would
  reconcile in the background.

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
