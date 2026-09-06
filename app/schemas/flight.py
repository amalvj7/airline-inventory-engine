import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import FlightStatus


class InventoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    physical_capacity: int
    overbooking_factor: Decimal
    booking_limit: int
    booked_count: int
    remaining: int
    is_oversold: bool


class FlightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    flight_number: str
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    status: FlightStatus
    inventory: InventoryOut


class FlightCreate(BaseModel):
    flight_number: str = Field(max_length=10)
    origin: str = Field(min_length=3, max_length=3)
    destination: str = Field(min_length=3, max_length=3)
    departure_time: datetime
    arrival_time: datetime
    physical_capacity: int = Field(gt=0)
    overbooking_factor: Decimal = Field(default=Decimal("0"), ge=0)


class OverbookingUpdate(BaseModel):
    overbooking_factor: Decimal = Field(ge=0, le=Decimal("2"))