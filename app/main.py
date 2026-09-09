import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

import app.models
from app.api import bookings, demo, flights, ops
from app.api.errors import register_error_handlers
from app.config import settings
from app.database import engine

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(
    title="Airline Multi-Leg Seat Inventory & Overbooking Engine",
    version="0.1.0",
    description=(
        "Concurrency-safe seat claiming across shared flight legs, "
        "with per-flight overbooking policy and bump resolution."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,   # no cookies, no auth header — don't enable what we don't use
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Idempotency-Key"],
)

register_error_handlers(app)
app.include_router(flights.router)
app.include_router(bookings.router)
app.include_router(ops.router)
app.include_router(demo.router)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}