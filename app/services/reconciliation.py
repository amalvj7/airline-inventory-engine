import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BookingLeg, Flight, FlightInventory
from app.models.enums import CONSUMING_LEG_STATUSES


@dataclass(frozen=True)
class FlightReconciliation:
    flight_id: uuid.UUID
    flight_number: str
    physical_capacity: int
    booking_limit: int
    stored_booked: int
    expected_booked: int
    remaining: int
    oversold: bool

    @property
    def drift(self) -> int:
        return self.stored_booked - self.expected_booked

    @property
    def ok(self) -> bool:
        return self.drift == 0


@dataclass(frozen=True)
class ReconciliationReport:
    flights: list[FlightReconciliation]

    @property
    def ok(self) -> bool:
        return all(f.ok for f in self.flights)

    @property
    def mismatches(self) -> list[FlightReconciliation]:
        return [f for f in self.flights if not f.ok]


def reconcile(session: Session) -> ReconciliationReport:
    """Compare every flight's stored counter against its actual consuming legs."""
    counts_subq = (
        select(
            BookingLeg.flight_id.label("flight_id"),
            func.count(BookingLeg.id).label("actual"),
        )
        .where(BookingLeg.status.in_(CONSUMING_LEG_STATUSES))
        .group_by(BookingLeg.flight_id)
        .subquery()
    )

    rows = session.execute(
        select(
            Flight.id,
            Flight.flight_number,
            FlightInventory.physical_capacity,
            FlightInventory.booking_limit,
            FlightInventory.booked_count,
            func.coalesce(counts_subq.c.actual, 0),
        )
        .join(FlightInventory, FlightInventory.flight_id == Flight.id)
        .outerjoin(counts_subq, counts_subq.c.flight_id == Flight.id)
        .order_by(Flight.flight_number)
    ).all()

    return ReconciliationReport(
        flights=[
            FlightReconciliation(
                flight_id=fid,
                flight_number=number,
                physical_capacity=capacity,
                booking_limit=limit,
                stored_booked=stored,
                expected_booked=actual,
                remaining=limit - stored,
                oversold=stored > capacity,
            )
            for fid, number, capacity, limit, stored, actual in rows
        ]
    )