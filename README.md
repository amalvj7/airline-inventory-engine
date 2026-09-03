# Airline Multi-Leg Seat Inventory & Overbooking Engine

## 1. Overview

A backend service for managing airline bookings and shared seat inventory across multi-leg itineraries.

The system handles multi-leg bookings, configurable flight-level overbooking, cancellation, rebooking, bumped passengers, and inventory reconciliation.

The main focus is maintaining consistent inventory when multiple bookings access the same flight concurrently.







## 2. Scope

### In Scope

* Create and manage flights and their seat inventory.
* Book single-leg and multi-leg itineraries.
* Support shared inventory across connecting itineraries.
* Configure overbooking limits per flight.
* Handle cancellations and rebookings.
* Handle bumped passengers when a flight is oversold.
* Ensure concurrent bookings do not cause inconsistent inventory.
* Reconcile inventory against booking records.

### Out of Scope

* Real GDS/airline system integration.
* Payment and ticketing.
* Complex fare/pricing logic.
* Actual seat selection or seat-map management.
* Production-scale distributed deployment.






## 3. Key Assumptions

* Each flight has one inventory record identified by `flight_id`.
* A multi-leg booking consumes inventory on every flight leg in the itinerary.
* A booking is confirmed only when inventory is available on all required legs.
* Inventory updates for a booking are handled within a database transaction.
* Concurrent bookings on the same flight are controlled using row-level locking.
* Overbooking is configured independently for each flight.
* Existing confirmed bookings are not automatically cancelled when the overbooking limit is reduced.
* For this project, bumped passengers are resolved using a simple priority-based rule.
* Cancellation and rebooking updates are performed atomically to keep booking and inventory records consistent.






## 4. Proposed Approach

The system will use a relational database to maintain flights, inventory, passengers, and bookings.

For a booking request, the required flight legs will be checked together inside a database transaction. Inventory rows will be locked while checking and updating availability so that concurrent bookings cannot oversell the same flight.

Multi-leg bookings, cancellations, and rebookings will be handled atomically to keep booking records and flight inventory consistent.

A reconciliation process will compare the stored inventory with active booking records to detect any mismatch.



## 5. Project Structure


airline-inventory-engine/
├── app/
│   ├── models/
│   ├── services/
│   ├── api/
│   └── database/
├── tests/
├── README.md
├── DESIGN.md
└── requirements.txt

The application logic will be separated into API, service, database, and model layers. Tests will cover the main booking, concurrency, cancellation, rebooking, overbooking, and reconciliation scenarios.

#(there may some changes in the structure)




## 6. Setup

### Requirements

* Python 3.x
* PostgreSQL
* Git

### Installation

Clone the repository and install the project dependencies:

```bash
git clone <repository-url>
cd airline-inventory-engine
pip install -r requirements.txt
```

Configure the database connection using the environment variables provided in `.env`.

### Database Setup

Create the PostgreSQL database and run the required database migrations/setup scripts.

### Run

```bash
# command will be added after the application setup is finalized
```




## 7. Running the Project

After completing the setup and configuring the database, start the application using:

```bash
# command will be added after implementation
```

The API will expose endpoints for flight inventory, booking, cancellation, rebooking, overbooking configuration, bump resolution, and reconciliation.



## 8. API Overview

| Method  | Endpoint                           | Purpose                                        |
| ------- | ---------------------------------- | ---------------------------------------------- |
| `POST`  | `/flights`                         | Create a flight and its inventory              |
| `GET`   | `/flights/{flight_id}`             | Get flight and inventory details               |
| `POST`  | `/bookings`                        | Create a single or multi-leg booking           |
| `GET`   | `/bookings/{booking_id}`           | Get booking details                            |
| `POST`  | `/bookings/{booking_id}/cancel`    | Cancel a booking                               |
| `POST`  | `/bookings/{booking_id}/rebook`    | Rebook an unavailable/cancelled leg            |
| `PATCH` | `/flights/{flight_id}/overbooking` | Update the flight's overbooking limit          |
| `POST`  | `/flights/{flight_id}/bump`        | Resolve passengers when the flight is oversold |
| `GET`   | `/reconciliation`                  | Check inventory against booking records        |




## 9. Testing

The test suite will cover the main booking and inventory scenarios:

* Successful single-leg and multi-leg bookings.
* Rejection when any required leg has no available inventory.
* Concurrent booking attempts for the last available inventory.
* Concurrent bookings sharing the same flight leg.
* Cancellation and inventory release.
* Rebooking of an unavailable leg.
* Changes to flight-level overbooking limits.
* Bumped passenger resolution for oversold flights.
* Inventory reconciliation against active booking records.

Concurrency tests will verify that multiple requests cannot successfully claim the same remaining inventory.







## 10. Demo Scenarios

The final demo will cover the following scenarios:

1. Last-seat concurrency — Two concurrent bookings attempt to claim the last available inventory. Only one should succeed.

2. Shared-leg concurrency — Different itineraries attempt to book the same flight leg concurrently without causing an oversell.

3. Multi-leg cancellation — Cancelling a booking releases the inventory used by its legs and leaves the booking records in a consistent state.

4. Overbooking limit change — Change the overbooking limit of a flight while bookings already exist and verify that the new limit is applied.

5. Reconciliation — Compare the maintained flight inventory with active booking records and confirm that the final state is consistent.
