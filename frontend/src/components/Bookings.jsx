import { useState } from "react";
import { api } from "../api";
import { Feedback } from "./Feedback";

const LEG_CLASS = {
  CONFIRMED: "badge-open",
  BUMPED: "badge-full",
  CANCELLED: "badge-muted",
  REBOOKED: "badge-muted",
};

export function Bookings({ bookings, flights, passengers, onChanged }) {
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const flightNumber = (id) => flights.find((f) => f.id === id)?.flight_number ?? id.slice(0, 8);
  const passengerName = (id) => passengers.find((p) => p.id === id)?.name ?? "unknown";

  async function cancel(booking) {
    setBusy(booking.id);
    setError(null);
    setSuccess(null);
    try {
      await api.cancel(booking.id);
      setSuccess(`Cancelled ${passengerName(booking.passenger_id)}'s itinerary — seats released`);
      await onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="card">
      <h2>
        Bookings <span className="count">{bookings.length}</span>
      </h2>
      <p className="hint">
        Cancelling releases every leg of the itinerary. It is idempotent — cancelling an already
        cancelled booking succeeds and releases nothing.
      </p>

      <Feedback error={error} success={success} />

      {bookings.length === 0 ? (
        <p className="empty">No bookings yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Passenger</th>
                <th>Itinerary</th>
                <th>Status</th>
                <th>Booked</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {bookings.map((booking) => (
                <tr key={booking.id}>
                  <td>{passengerName(booking.passenger_id)}</td>
                  <td className="mono">
                    {booking.legs.map((leg, i) => (
                      <span key={leg.id}>
                        {i > 0 && <span className="arrow"> → </span>}
                        <span className={`badge ${LEG_CLASS[leg.status] ?? "badge-muted"}`}>
                          {flightNumber(leg.flight_id)}
                        </span>
                      </span>
                    ))}
                  </td>
                  <td>
                    <span className={`badge ${booking.status === "CONFIRMED" ? "badge-open" : "badge-muted"}`}>
                      {booking.status}
                    </span>
                  </td>
                  <td className="muted">{new Date(booking.created_at).toLocaleTimeString()}</td>
                  <td className="actions">
                    <button
                      className="btn btn-sm"
                      onClick={() => cancel(booking)}
                      disabled={busy !== null || booking.status === "CANCELLED"}
                    >
                      {busy === booking.id ? "…" : "Cancel"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
