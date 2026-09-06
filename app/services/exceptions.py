import uuid


class BookingError(Exception):
    """Base for all booking domain errors."""


class FlightNotFound(BookingError):
    def __init__(self, flight_id: uuid.UUID):
        self.flight_id = flight_id
        super().__init__(f"Flight {flight_id} not found")


class PassengerNotFound(BookingError):
    def __init__(self, passenger_id: uuid.UUID):
        self.passenger_id = passenger_id
        super().__init__(f"Passenger {passenger_id} not found")


class LegUnavailable(BookingError):
    def __init__(self, flight_id: uuid.UUID, flight_number: str, limit: int, booked: int):
        self.flight_id = flight_id
        self.flight_number = flight_number
        self.booking_limit = limit
        self.booked_count = booked
        super().__init__(f"No inventory on flight {flight_number} ({booked}/{limit})")


class InvalidItinerary(BookingError):
    """Empty leg list, duplicate flights, or otherwise malformed request."""



class BookingNotFound(BookingError):
    def __init__(self, booking_id: uuid.UUID):
        self.booking_id = booking_id
        super().__init__(f"Booking {booking_id} not found")



class InvalidOverbookingFactor(BookingError):
    """Factor was negative."""



class LegNotFound(BookingError):
    def __init__(self, leg_id: uuid.UUID):
        self.leg_id = leg_id
        super().__init__(f"Booking leg {leg_id} not found")