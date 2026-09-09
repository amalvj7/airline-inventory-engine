import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.race import MAX_CLIENTS, MIN_CLIENTS


class RaceGroupIn(BaseModel):
    flight_ids: list[uuid.UUID] = Field(min_length=1)
    clients: int = Field(default=5, ge=1, le=MAX_CLIENTS)
    label: str | None = None


class RaceRequest(BaseModel):
    """Either `groups` for an itinerary race, or `flight_id` + `clients` as
    shorthand for the single-flight case."""

    flight_id: uuid.UUID | None = None
    clients: int = Field(default=10, ge=MIN_CLIENTS, le=MAX_CLIENTS)
    groups: list[RaceGroupIn] | None = None

    @model_validator(mode="after")
    def _require_one_shape(self):
        if self.groups is None and self.flight_id is None:
            raise ValueError("provide either flight_id or groups")
        return self


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    booking_limit: int
    booked_count: int
    remaining: int
    is_oversold: bool


class FlightOutcomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    flight_id: uuid.UUID
    flight_number: str
    before: SnapshotOut
    after: SnapshotOut
    seats_claimed: int


class GroupOutcomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    label: str
    flight_numbers: list[str]
    clients: int
    accepted: int
    rejected: int


class RaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    clients: int
    accepted: int
    rejected: int
    failed: int
    groups: list[GroupOutcomeOut]
    flights: list[FlightOutcomeOut]
    seats_claimed: int
    seats_expected: int
    within_limit: bool
    consistent: bool
    elapsed_ms: int
    errors: list[str]
