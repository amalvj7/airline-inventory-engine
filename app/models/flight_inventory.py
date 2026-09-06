import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FlightInventory(Base):
    __tablename__ = "flight_inventory"

    flight_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("flights.id", ondelete="CASCADE"),
        primary_key=True,
    )

    physical_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    overbooking_factor: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, default=0
    )
    booking_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    booked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    flight: Mapped["Flight"] = relationship(back_populates="inventory")  # noqa: F821

    __table_args__ = (
        CheckConstraint("physical_capacity > 0", name="ck_inv_capacity_positive"),
        CheckConstraint("overbooking_factor >= 0", name="ck_inv_factor_non_negative"),
        CheckConstraint("booked_count >= 0", name="ck_inv_booked_non_negative"),
        CheckConstraint("booking_limit > 0", name="ck_inv_limit_positive"),
    )

    @staticmethod
    def compute_booking_limit(physical_capacity: int, overbooking_factor: float) -> int:
        """floor(capacity × (1 + factor)). Floor never sells an unauthorised seat."""
        return int(physical_capacity * (1 + float(overbooking_factor)))

    @property
    def remaining(self) -> int:
        """May be negative if the factor was lowered below seats already sold."""
        return self.booking_limit - self.booked_count

    @property
    def is_available(self) -> bool:
        return self.booked_count < self.booking_limit

    @property
    def is_oversold(self) -> bool:
        """More confirmed seats than the aircraft physically holds."""
        return self.booked_count > self.physical_capacity