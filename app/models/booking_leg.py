import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin
from app.models.enums import CONSUMING_LEG_STATUSES, FareClass, LegStatus


class BookingLeg(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "booking_legs"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    flight_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("flights.id", ondelete="RESTRICT"),
        nullable=False,
    )

    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    fare_class: Mapped[FareClass] = mapped_column(
        SAEnum(FareClass, name="fare_class"), nullable=False, default=FareClass.M
    )
    status: Mapped[LegStatus] = mapped_column(
        SAEnum(LegStatus, name="leg_status"), nullable=False, default=LegStatus.CONFIRMED
    )

    booking: Mapped["Booking"] = relationship(back_populates="legs")  # noqa: F821
    flight: Mapped["Flight"] = relationship()  # noqa: F821

    __table_args__ = (
        UniqueConstraint("booking_id", "sequence", name="uq_leg_booking_sequence"),
        CheckConstraint("sequence > 0", name="ck_leg_sequence_positive"),
        Index("ix_legs_flight_status", "flight_id", "status"),
    )

    @property
    def consumes_inventory(self) -> bool:
        return self.status in CONSUMING_LEG_STATUSES