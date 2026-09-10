from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.exceptions import (
    BookingNotFound,
    DemoDisabled,
    FlightNotFound,
    InvalidFlightTimes,
    InvalidItinerary,
    InvalidOverbookingFactor,
    LegNotFound,
    LegUnavailable,
    PassengerNotFound,
)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(LegUnavailable)
    async def _leg_unavailable(request: Request, exc: LegUnavailable):
        return JSONResponse(
            status_code=409,
            content={
                "error": "LEG_UNAVAILABLE",
                "detail": str(exc),
                "flight_id": str(exc.flight_id),
                "flight_number": exc.flight_number,
                "booking_limit": exc.booking_limit,
                "booked_count": exc.booked_count,
            },
        )

    for exc_type, code, label in (
        (FlightNotFound, 404, "FLIGHT_NOT_FOUND"),
        (PassengerNotFound, 404, "PASSENGER_NOT_FOUND"),
        (BookingNotFound, 404, "BOOKING_NOT_FOUND"),
        (LegNotFound, 404, "LEG_NOT_FOUND"),
        (DemoDisabled, 404, "DEMO_DISABLED"),
        (InvalidItinerary, 400, "INVALID_ITINERARY"),
        (InvalidOverbookingFactor, 400, "INVALID_OVERBOOKING_FACTOR"),
        (InvalidFlightTimes, 400, "INVALID_FLIGHT_TIMES"),
    ):

        def _make(code: int, label: str):
            async def handler(request: Request, exc: Exception):
                return JSONResponse(
                    status_code=code, content={"error": label, "detail": str(exc)}
                )
            return handler

        app.add_exception_handler(exc_type, _make(code, label))