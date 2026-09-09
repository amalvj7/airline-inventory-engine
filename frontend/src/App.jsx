import { useCallback, useEffect, useState } from "react";
import { api, apiBaseUrl } from "./api";

function formatTime(iso) {
  return new Date(iso).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function InventoryState({ inventory }) {
  if (inventory.is_oversold) return <span className="badge badge-oversold">oversold</span>;
  if (inventory.remaining === 0) return <span className="badge badge-full">full</span>;
  return <span className="badge badge-open">{inventory.remaining} left</span>;
}

/** Seats sold against the booking limit, which may exceed physical capacity. */
function SeatBar({ inventory }) {
  const { physical_capacity: capacity, booking_limit: limit, booked_count: booked } = inventory;
  const scale = Math.max(limit, booked, 1);
  return (
    <div className="seatbar" title={`${booked} booked / ${limit} limit / ${capacity} seats`}>
      <div className="seatbar-fill" style={{ width: `${(booked / scale) * 100}%` }} />
      <div className="seatbar-capacity" style={{ left: `${(capacity / scale) * 100}%` }} />
    </div>
  );
}

export default function App() {
  const [flights, setFlights] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadedAt, setLoadedAt] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setFlights(await api.flights());
      setLoadedAt(new Date());
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="page">
      <header className="header">
        <div>
          <h1>Seat Inventory</h1>
          <p className="subtitle">
            Live from <code>{apiBaseUrl}</code>
            {loadedAt && <> · updated {loadedAt.toLocaleTimeString()}</>}
          </p>
        </div>
        <button className="btn" onClick={load} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </header>

      {error && (
        <div className="notice notice-error">
          <strong>{error.code ?? "Request failed"}</strong>
          <span>{error.message}</span>
        </div>
      )}

      {loading && flights.length === 0 && (
        <div className="notice">
          Contacting the API… the first request after a while can take up to a minute while
          the free instance wakes up.
        </div>
      )}

      {flights.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Flight</th>
              <th>Route</th>
              <th>Departs</th>
              <th className="num">Seats</th>
              <th className="num">Limit</th>
              <th className="num">Booked</th>
              <th className="num">Remaining</th>
              <th>Load</th>
              <th>State</th>
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
                <td className="num mono">{flight.inventory.booking_limit}</td>
                <td className="num mono">{flight.inventory.booked_count}</td>
                <td className="num mono">{flight.inventory.remaining}</td>
                <td>
                  <SeatBar inventory={flight.inventory} />
                </td>
                <td>
                  <InventoryState inventory={flight.inventory} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <footer className="footer">
        <span>
          <strong>Limit</strong> = floor(seats × (1 + overbooking factor)). The marker on each
          bar is physical capacity — bookings past it are deliberate overselling.
        </span>
      </footer>
    </div>
  );
}
