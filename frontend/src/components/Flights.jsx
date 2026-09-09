import { useState } from "react";
import { api } from "../api";
import { Feedback } from "./Feedback";

function formatTime(iso) {
  return new Date(iso).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function State({ inventory }) {
  if (inventory.is_oversold) return <span className="badge badge-oversold">oversold</span>;
  if (inventory.remaining <= 0) return <span className="badge badge-full">full</span>;
  return <span className="badge badge-open">{inventory.remaining} left</span>;
}

/** Seats sold against the booking limit; the tick marks physical capacity. */
function SeatBar({ inventory }) {
  const { physical_capacity: capacity, booking_limit: limit, booked_count: booked } = inventory;
  const scale = Math.max(limit, booked, 1);
  return (
    <div className="seatbar" title={`${booked} booked · limit ${limit} · ${capacity} seats`}>
      <div
        className={`seatbar-fill${booked > capacity ? " seatbar-over" : ""}`}
        style={{ width: `${Math.min((booked / scale) * 100, 100)}%` }}
      />
      <div className="seatbar-capacity" style={{ left: `${(capacity / scale) * 100}%` }} />
    </div>
  );
}

export function Flights({ flights, onChanged }) {
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  async function run(key, action, message) {
    setBusy(key);
    setError(null);
    setSuccess(null);
    try {
      const result = await action();
      setSuccess(message(result));
      await onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  function changeFactor(flight) {
    const raw = window.prompt(
      `Overbooking factor for ${flight.flight_number}  (0 to 2)\n\n` +
        `limit = floor(${flight.inventory.physical_capacity} × (1 + factor))\n` +
        `Currently ${flight.inventory.overbooking_factor}. Lowering it below what is ` +
        `already sold is allowed — the flight becomes oversold.`,
      flight.inventory.overbooking_factor,
    );
    if (raw === null) return;
    run(
      `factor-${flight.id}`,
      () => api.setOverbooking(flight.id, raw.trim()),
      (f) => `${f.flight_number}: limit is now ${f.inventory.booking_limit}`,
    );
  }

  function bump(flight) {
    run(
      `bump-${flight.id}`,
      () => api.bump(flight.id),
      (r) =>
        r.overage === 0
          ? `${flight.flight_number} is not oversold — nobody bumped`
          : `${flight.flight_number}: bumped ${r.bumped_leg_ids.length} passenger(s), ` +
            `${r.cascaded_leg_ids.length} connecting leg(s) affected`,
    );
  }

  return (
    <section className="card">
      <h2>Flights</h2>
      <p className="hint">
        <strong>Limit</strong> = floor(seats × (1 + overbooking factor)). The tick on each bar is
        physical capacity — a bar past the tick is deliberate overselling.
      </p>

      <Feedback error={error} success={success} />

      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Flight</th>
              <th>Route</th>
              <th>Departs</th>
              <th className="num">Seats</th>
              <th className="num">Factor</th>
              <th className="num">Limit</th>
              <th className="num">Booked</th>
              <th className="num">Left</th>
              <th>Load</th>
              <th>State</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {flights.map((flight) => (
              <tr key={flight.id}>
                <td className="mono strong">{flight.flight_number}</td>
                <td className="mono">
                  {flight.origin} <span className="arrow">→</span> {flight.destination}
                </td>
                <td className="muted">{formatTime(flight.departure_time)}</td>
                <td className="num mono">{flight.inventory.physical_capacity}</td>
                <td className="num mono">{Number(flight.inventory.overbooking_factor)}</td>
                <td className="num mono">{flight.inventory.booking_limit}</td>
                <td className="num mono">{flight.inventory.booked_count}</td>
                <td className="num mono">{flight.inventory.remaining}</td>
                <td>
                  <SeatBar inventory={flight.inventory} />
                </td>
                <td>
                  <State inventory={flight.inventory} />
                </td>
                <td className="actions">
                  <button
                    className="btn btn-sm"
                    onClick={() => changeFactor(flight)}
                    disabled={busy !== null}
                  >
                    {busy === `factor-${flight.id}` ? "…" : "Factor"}
                  </button>
                  <button
                    className="btn btn-sm"
                    onClick={() => bump(flight)}
                    disabled={busy !== null}
                    title="Resolve an oversold flight at departure"
                  >
                    {busy === `bump-${flight.id}` ? "…" : "Bump"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
