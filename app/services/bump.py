import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Booking, BookingLeg
from app.models.enums import CONSUMING_LEG_STATUSES, BookingStatus, LegStatus
from app.policies.bump import BumpPolicy, PriorityBumpPolicy
from app.repositories.inventory import lock_inventories
from app.services.exceptions import FlightNotFound


@dataclass(frozen=True)
class BumpResult:
    flight_id: uuid.UUID
    overage: int
    bumped_leg_ids: list[uuid.UUID]
    cascaded_leg_ids: list[uuid.UUID]


def resolve_oversold_flight(
    session: Session,
    flight_id: uuid.UUID,
    policy: BumpPolicy | None = None,
) -> BumpResult:
    """
    Deny boarding to the lowest-priority passengers on an oversold flight.

    A BUMPED leg continues to consume inventory until it is rebooked or
    cancelled, so a passenger always holds exactly one seat somewhere.
    Because itineraries are atomic, bumping one leg marks the rest of that
    passenger's itinerary as pending resolution.
    """
    policy = policy or PriorityBumpPolicy()

    inv = lock_inventories(session, [flight_id]).get(flight_id)
    if inv is None:
        raise FlightNotFound(flight_id)

    overage = inv.booked_count - inv.physical_capacity
    if overage <= 0:
        return BumpResult(flight_id, 0, [], [])

    legs = session.execute(
        select(BookingLeg)
        .where(BookingLeg.flight_id == flight_id)
        .where(BookingLeg.status.in_(CONSUMING_LEG_STATUSES))
        .options(joinedload(BookingLeg.booking).joinedload(Booking.passenger))
    ).scalars().all()

    victims = sorted(legs, key=policy.sort_key, reverse=True)[:overage]

    bumped_ids, cascaded_ids = [], []
    for leg in victims:
        leg.status = LegStatus.BUMPED
        bumped_ids.append(leg.id)

        booking = leg.booking
        booking.status = BookingStatus.BUMPED_PENDING
        for sibling in booking.legs:
            if sibling.id != leg.id and sibling.status == LegStatus.CONFIRMED:
                cascaded_ids.append(sibling.id)

    session.flush()
    return BumpResult(flight_id, overage, bumped_ids, cascaded_ids)