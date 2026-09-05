from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin
from app.models.enums import FlightStatus


class Flight(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "flights"

    flight_number: Mapped[str] = mapped_column(String(10), nullable=False)
    origin: Mapped[str] = mapped_column(String(3), nullable=False)
    destination: Mapped[str] = mapped_column(String(3), nullable=False)
    departure_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    arrival_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[FlightStatus] = mapped_column(
        SAEnum(FlightStatus, name="flight_status"),
        nullable=False,
        default=FlightStatus.SCHEDULED,
    )

    inventory: Mapped["FlightInventory"] = relationship(  # noqa: F821
        back_populates="flight",
        uselist=False,
        cascade="all, delete-orphan",
    )
    __table_args__ = (
        CheckConstraint("origin <> destination", name="ck_flight_distinct_endpoints"),
        CheckConstraint("arrival_time > departure_time", name="ck_flight_time_order"),
        Index("ix_flights_route_departure", "origin", "destination", "departure_time"),
    )