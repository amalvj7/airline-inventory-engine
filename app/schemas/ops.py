import uuid

from pydantic import BaseModel, ConfigDict


class PassengerCreate(BaseModel):
    name: str
    tier: str = "STANDARD"


class PassengerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    tier: str


class BumpOut(BaseModel):
    flight_id: uuid.UUID
    overage: int
    bumped_leg_ids: list[uuid.UUID]
    cascaded_leg_ids: list[uuid.UUID]


class FlightReconciliationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    flight_id: uuid.UUID
    flight_number: str
    physical_capacity: int
    booking_limit: int
    stored_booked: int
    expected_booked: int
    remaining: int
    oversold: bool
    drift: int
    ok: bool


class ReconciliationOut(BaseModel):
    ok: bool
    flights: list[FlightReconciliationOut]