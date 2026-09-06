import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BookingStatus, FareClass, LegStatus


class LegIn(BaseModel):
    flight_id: uuid.UUID
    fare_class: FareClass = FareClass.M


class BookingCreate(BaseModel):
    passenger_id: uuid.UUID
    legs: list[LegIn] = Field(min_length=1)


class LegOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    flight_id: uuid.UUID
    sequence: int
    fare_class: FareClass
    status: LegStatus


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    passenger_id: uuid.UUID
    status: BookingStatus
    created_at: datetime
    legs: list[LegOut]


class RebookRequest(BaseModel):
    leg_id: uuid.UUID
    new_flight_id: uuid.UUID