

## 1. Architecture Overview
The system will be implemented as a backend API with a relational database.

Client
  |
  v
API Layer
  |
  v
Service Layer
  |
  v
PostgreSQL Database

The API layer handles requests, while the service layer contains booking, cancellation, rebooking, overbooking, and reconciliation logic.

PostgreSQL will be responsible for maintaining the shared flight inventory and ensuring concurrent booking operations are handled safely using transactions and row-level locking.






## 2. Data Model
The system uses five main entities:

* `PASSENGER` — stores passenger details.
* `BOOKING` — represents a passenger's booking/itinerary.
* `BOOKING_LEG` — connects a booking to each flight used by the itinerary.
* `FLIGHT` — stores individual flight-leg information.
* `FLIGHT_INVENTORY` — stores the physical capacity and booking inventory for each flight.

### Relationships
PASSENGER 1 ──── N BOOKING
BOOKING   1 ──── N BOOKING_LEG
FLIGHT    1 ──── N BOOKING_LEG
FLIGHT    1 ──── 1 FLIGHT_INVENTORY

BOOKING_LEG is used to represent the many-to-many relationship between bookings and flights. The sequence field maintains the order of legs in a multi-leg itinerary.

FLIGHT_INVENTORY.flight_id is both the primary key and a foreign key to FLIGHT.id, since each flight has one inventory record.

### Main Fields
PASSENGER
- id (PK)
- name

BOOKING
- id (PK)
- passenger_id (FK)
- status
- created_at

BOOKING_LEG
- id (PK)
- booking_id (FK)
- flight_id (FK)
- sequence
- status

FLIGHT
- id (PK)
- flight_number
- origin
- destination
- departure_time
- arrival_time
- status

FLIGHT_INVENTORY
- flight_id (PK, FK)
- physical_capacity
- overbooking_factor
- booking_limit
- remaining_inventory






## 3. Inventory & Overbooking Design

Each flight has a separate inventory record. The inventory is based on the physical capacity of the aircraft and a configurable overbooking factor.

booking_limit = physical_capacity × (1 + overbooking_factor)

For example:
Physical capacity = 100
Overbooking factor = 10%

Booking limit = 110

remaining_inventory represents how many additional bookings can currently be accepted.

The overbooking factor is configurable for each flight rather than using a global value.

If the overbooking limit is reduced after bookings already exist, existing bookings will not be automatically cancelled. New bookings will be restricted based on the updated limit, and the flight can be marked as oversold for further handling.

At departure, if confirmed passengers exceed physical capacity, the bump-resolution process will be used according to the priority rule defined for this project.






## 4. Booking & Transaction Flow

A booking request may contain one or more flight legs. All required legs must be available before the booking is confirmed.

For a multi-leg booking, the operation follows this flow:
Booking Request
      |
      v
Identify required flight legs
      |
      v
Start Database Transaction
      |
      v
Lock inventory rows for all legs
      |
      v
Check remaining inventory
      |
   ┌──┴──┐
   |     |
Available  Not Available
   |          |
   v          v
Reserve     Rollback
all legs    transaction
   |
   v
Create booking + booking legs
   |
   v
Commit

If any required leg does not have available inventory, the complete transaction is rolled back. This prevents a situation where one leg is reserved while another leg of the same itinerary fails.

Inventory rows will be locked while they are being checked and updated. This prevents two concurrent booking requests from both successfully claiming the same remaining inventory.

For multiple inventory rows, locks will be acquired in a consistent order to reduce the possibility of deadlocks.







## 5. Cancellation & Rebooking

### Cancellation

Cancelling a booking will update both the booking records and the corresponding flight inventory within a single transaction.

For a multi-leg booking, all active legs belonging to the booking will be cancelled and their inventory will be released.

If only one leg is cancelled externally, the dependent legs will not be left active without a valid itinerary. The system will either cancel the dependent itinerary or rebook the affected leg according to the available rebooking option.

### Rebooking

When a flight leg needs to be changed, the system will:

1. Find a suitable replacement flight.
2. Check availability on the replacement flight.
3. Lock the required inventory rows.
4. Release the old flight inventory.
5. Reserve the replacement flight.
6. Update the corresponding `BOOKING_LEG`.

These changes will be performed within a transaction so that a failed rebooking does not leave the booking in a partially updated state.








## 6. Bumped Passenger Resolution

When confirmed passengers exceed the physical capacity of a flight at departure, the system will identify passengers who need to be bumped.

A simple priority-based rule will be used for this project. Passengers with lower priority will be selected first for bumping.

The affected booking leg will be marked as `BUMPED`, and the system will attempt to resolve the passenger through rebooking. If a suitable replacement is not available, the booking will be marked according to the final resolution status.

The bumping policy is intentionally kept simple since the project focuses on inventory management rather than airline revenue or passenger compensation optimization.






## 7. Concurrency Control

Concurrency is handled at the database level using transactions and row-level locking.

Before checking or updating inventory, the relevant `FLIGHT_INVENTORY` rows will be locked. This ensures that two concurrent booking requests cannot both claim the same remaining inventory.

For example, if a flight has only one remaining booking:
Request A → Lock inventory → Reserve → Commit
Request B → Wait for lock → Check inventory → Reject

For multi-leg bookings, all required inventory rows will be locked before making the final availability decision. Locks will be acquired in a consistent order to reduce the possibility of deadlocks.

This ensures that the final inventory remains consistent even when multiple bookings access shared flight legs concurrently.





## 8. Reconciliation

A reconciliation check will be used to verify that the maintained flight inventory matches the booking records.

For each flight:
Expected remaining inventory
= booking_limit - active booking legs

The calculated value will be compared with `remaining_inventory` stored in `FLIGHT_INVENTORY`.

Stored inventory == Expected inventory
        ↓
       PASS

Stored inventory != Expected inventory
        ↓
       MISMATCH

This check helps identify inventory inconsistencies after bookings, cancellations, rebookings, and concurrency operations.







## 9. Design Trade-offs

* Relational database: We chose PostgreSQL for transactional consistency and relationships between bookings and flights. This gives us strong consistency and locking support, but requires a more structured schema and makes schema changes less flexible than a NoSQL approach.

* Stored remaining_inventory:** Provides simpler and faster availability checks, but introduces the possibility of the stored value becoming inconsistent with booking records. A reconciliation process is therefore included.

* Row-level locking: Prevents inconsistent inventory during concurrent bookings, but requests competing for the same flight may have to wait for the lock to be released.

* Single service architecture: Keeps the implementation simple and easy to test for the simulated network, but provides less independent scalability and service isolation than a distributed/microservice architecture.

* Simple bumping policy: A deterministic priority-based rule keeps the implementation simple and testable, but does not model the more complex prioritization used by real airlines.
