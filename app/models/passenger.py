from sqlalchemy import Enum as SAEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PassengerTier


class Passenger(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "passengers"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    tier: Mapped[PassengerTier] = mapped_column(
        SAEnum(PassengerTier, name="passenger_tier"),
        nullable=False,
        default=PassengerTier.STANDARD,
    )

    bookings: Mapped[list["Booking"]] = relationship(  # noqa: F821
        back_populates="passenger",
    )