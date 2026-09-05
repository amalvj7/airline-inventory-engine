from fastapi import FastAPI
from sqlalchemy import text

import app.models  # noqa: F401
from app.api import bookings, flights, ops
from app.api.errors import register_error_handlers
from app.database import engine

app = FastAPI(
    title="Airline Multi-Leg Seat Inventory & Overbooking Engine",
    version="0.1.0",
    description=(
        "Concurrency-safe seat claiming across shared flight legs, "
        "with per-flight overbooking policy and bump resolution."
    ),
)

register_error_handlers(app)
app.include_router(flights.router)
app.include_router(bookings.router)
app.include_router(ops.router)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}