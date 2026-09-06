import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FlightInventory


def lock_inventories(
    session: Session, flight_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, FlightInventory]:

    ordered_ids = sorted(set(flight_ids))

    stmt = (
        select(FlightInventory)
        .where(FlightInventory.flight_id.in_(ordered_ids))
        .order_by(FlightInventory.flight_id)
        .with_for_update()
    )

    rows = session.execute(stmt).scalars().all()
    return {row.flight_id: row for row in rows}


def get_inventory(session: Session, flight_id: uuid.UUID) -> FlightInventory | None:
    """Unlocked read. For display only — never for an availability decision."""
    return session.get(FlightInventory, flight_id)