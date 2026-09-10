import { useState } from "react";
import { api } from "../api";
import { Feedback } from "./Feedback";

const LEG_CLASS = {
  CONFIRMED: "badge-open",
  BUMPED: "badge-full",
  CANCELLED: "badge-muted",
  REBOOKED: "badge-muted",
};

/** Only a confirmed or bumped leg can move; cancelled and rebooked ones are settled. */
const REBOOKABLE = new Set(["CONFIRMED", "BUMPED"]);

export function Bookings({ bookings, flights, passengers, onChanged, title = "Bookings" }) {
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [rebooking, setRebooking] = useState(null); // { bookingId, legId }
  const [target, setTarget] = useState("");

  const flightOf = (id) => flights.find((f) => f.id === id);
  const flightNumber = (id) => flightOf(id)?.flight_number ?? id.slice(0, 8);
  const passengerOf = (id) => passengers.find((p) => p.id === id);

  async function run(key, action, message) {
    setBusy(key);
    setError(null);
    setSuccess(null);
    try {
      await action();
      setSuccess(message);
      await onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  function cancel(booking) {
    const who = passengerOf(booking.passenger_id)?.name ?? "passenger";
    run(booking.id, () => api.cancel(booking.id), `Cancelled ${who}'s itinerary — seats released`);
  }

  function startRebook(bookingId, leg) {
    setRebooking({ bookingId, legId: leg.id });
    setTarget("");
    setError(null);
    setSuccess(null);
  }

  function confirmRebook(booking, leg) {
    const from = flightNumber(leg.flight_id);
    const to = flightNumber(target);
    run(
      leg.id,
      () => api.rebook(booking.id, leg.id, target),
      `Leg moved ${from} → ${to}; the old seat was released and a new one claimed`,
    ).then(() => setRebooking(null));
  }

  return (
    <section className="card">
      <h2>
        {title} <span className="count">{bookings.length}</span>
      </h2>
      <p className="hint">
        Click a row for its legs. Cancelling releases every leg and is idempotent. Rebooking moves
        one leg to another flight — the old seat is released and a new one claimed in the same
        transaction, so it can be rejected if the replacement is full.
      </p>

      <Feedback error={error} success={success} />

      {bookings.length === 0 ? (
        <p className="empty">No bookings yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th />
                <th>Passenger</th>
                <th>Itinerary</th>
                <th>Status</th>
                <th>Booked</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {bookings.map((booking) => {
                const open = expanded === booking.id;
                const passenger = passengerOf(booking.passenger_id);
                return [
                  <tr key={booking.id} className="row-clickable"
                      onClick={() => setExpanded(open ? null : booking.id)}>
                    <td className="muted">{open ? "▾" : "▸"}</td>
                    <td>
                      {passenger?.name ?? "unknown"}
                      {passenger && <span className="badge badge-muted tier">{passenger.tier}</span>}
                    </td>
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
                    <td className="actions" onClick={(e) => e.stopPropagation()}>
                      <button className="btn btn-sm" onClick={() => cancel(booking)}
                              disabled={busy !== null || booking.status === "CANCELLED"}>
                        {busy === booking.id ? "…" : "Cancel"}
                      </button>
                    </td>
                  </tr>,

                  open && (
                    <tr key={`${booking.id}-detail`} className="row-detail">
                      <td />
                      <td colSpan={5}>
                        <div className="detail">
                          <div className="detail-meta">
                            <span><b>Booking</b> <code>{booking.id}</code></span>
                            <span><b>Passenger</b> <code>{booking.passenger_id}</code></span>
                            <span><b>Created</b> {new Date(booking.created_at).toLocaleString()}</span>
                          </div>
                          <table className="table table-inner">
                            <thead>
                              <tr>
                                <th className="num">Seq</th>
                                <th>Flight</th>
                                <th>Route</th>
                                <th>Fare</th>
                                <th>Status</th>
                                <th />
                              </tr>
                            </thead>
                            <tbody>
                              {booking.legs.map((leg) => {
                                const f = flightOf(leg.flight_id);
                                const isRebooking =
                                  rebooking?.bookingId === booking.id && rebooking?.legId === leg.id;
                                return (
                                  <tr key={leg.id}>
                                    <td className="num mono">{leg.sequence}</td>
                                    <td className="mono strong">{flightNumber(leg.flight_id)}</td>
                                    <td className="mono">{f ? `${f.origin}→${f.destination}` : "—"}</td>
                                    <td className="mono">{leg.fare_class}</td>
                                    <td>
                                      <span className={`badge ${LEG_CLASS[leg.status] ?? "badge-muted"}`}>
                                        {leg.status}
                                      </span>
                                    </td>
                                    <td className="actions">
                                      {isRebooking ? (
                                        <>
                                          <select value={target} onChange={(e) => setTarget(e.target.value)}
                                                  className="select-inline">
                                            <option value="">Move to…</option>
                                            {flights
                                              .filter((x) => x.id !== leg.flight_id)
                                              .map((x) => (
                                                <option key={x.id} value={x.id}>
                                                  {x.flight_number} · {x.origin}→{x.destination} ·{" "}
                                                  {x.inventory.remaining} left
                                                </option>
                                              ))}
                                          </select>
                                          <button className="btn btn-sm btn-primary"
                                                  disabled={!target || busy !== null}
                                                  onClick={() => confirmRebook(booking, leg)}>
                                            {busy === leg.id ? "…" : "Confirm"}
                                          </button>
                                          <button className="btn btn-sm" onClick={() => setRebooking(null)}>
                                            Cancel
                                          </button>
                                        </>
                                      ) : (
                                        <button className="btn btn-sm"
                                                disabled={busy !== null || !REBOOKABLE.has(leg.status)}
                                                title={REBOOKABLE.has(leg.status)
                                                  ? "Move this leg to another flight"
                                                  : `A ${leg.status} leg cannot be rebooked`}
                                                onClick={() => startRebook(booking.id, leg)}>
                                          Rebook
                                        </button>
                                      )}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </td>
                    </tr>
                  ),
                ];
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
