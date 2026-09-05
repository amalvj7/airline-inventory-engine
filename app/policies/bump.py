from typing import Protocol

from app.models import BookingLeg


class BumpPolicy(Protocol):
    def sort_key(self, leg: BookingLeg) -> tuple: ...


class PriorityBumpPolicy:
    """
    Deterministic total ordering. Legs sorting highest are bumped first:
      1. passenger tier      — STANDARD before GOLD before PLATINUM
      2. fare class          — cheapest fare first
      3. booking recency     — last booked, first bumped
      4. leg id              — final tie-break, guarantees a total order
    """

    def sort_key(self, leg: BookingLeg) -> tuple:
        return (
            leg.booking.passenger.tier.bump_rank,
            leg.fare_class.bump_rank,
            -leg.booking.created_at.timestamp(),
            str(leg.id),
        )