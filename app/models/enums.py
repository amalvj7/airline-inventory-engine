import enum


class PassengerTier(str, enum.Enum):
    PLATINUM = "PLATINUM"
    GOLD = "GOLD"
    STANDARD = "STANDARD"

    @property
    def bump_rank(self) -> int:
        return {"PLATINUM": 1, "GOLD": 2, "STANDARD": 3}[self.value]


class FlightStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    DEPARTED = "DEPARTED"
    CANCELLED = "CANCELLED"



class BookingStatus(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    BUMPED_PENDING = "BUMPED_PENDING"


class LegStatus(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    BUMPED = "BUMPED"
    REBOOKED = "REBOOKED"
    CANCELLED = "CANCELLED"


CONSUMING_LEG_STATUSES: frozenset[LegStatus] = frozenset(
    {LegStatus.CONFIRMED, LegStatus.BUMPED}
)


class FareClass(str, enum.Enum):
    Y = "Y"   # full economy
    M = "M"   # standard
    B = "B"   # discount

    @property
    def bump_rank(self) -> int:
        return {"Y": 1, "M": 2, "B": 3}[self.value]