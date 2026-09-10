import { useMemo, useState } from "react";

const TIER_CLASS = { PLATINUM: "badge-open", GOLD: "badge-full", STANDARD: "badge-muted" };

/** Legs in these states still hold a seat -- same rule the counter uses. */
const CONSUMING = new Set(["CONFIRMED", "BUMPED"]);

export function Passengers({ passengers, bookings, flights }) {
  const [selectedId, setSelectedId] = useState("");

  const flightOf = (id) => flights.find((f) => f.id === id);
  const selected = passengers.find((p) => p.id === selectedId);

  const theirs = useMemo(
    () => bookings.filter((b) => b.passenger_id === selectedId),
    [bookings, selectedId],
  );

  const seatsHeld = theirs.reduce(
    (n, b) => n + b.legs.filter((l) => CONSUMING.has(l.status)).length,
    0,
  );
  const active = theirs.filter((b) => b.status !== "CANCELLED").length;

  return (
    <section className="card">
      <h2>
        Passengers <span className="count">{passengers.length}</span>
      </h2>
      <p className="hint">
        Tier decides bump priority only — it gives no advantage claiming a seat. A leg holds
        inventory while it is CONFIRMED or BUMPED; CANCELLED and REBOOKED legs hold nothing.
      </p>

      <label className="field">
        <span>Passenger</span>
        <select value={selectedId} onChange={(e) => setSelectedId(e.target.value)}>
          <option value="">Select a passenger…</option>
          {passengers.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} · {p.tier}
            </option>
          ))}
        </select>
      </label>

      {selected && (
        <div className="detail">
          <div className="detail-meta">
            <span>
              <b>Name</b> {selected.name}
            </span>
            <span>
              <b>Tier</b>{" "}
              <span className={`badge ${TIER_CLASS[selected.tier] ?? "badge-muted"}`}>
                {selected.tier}
              </span>
            </span>
            <span>
              <b>Id</b> <code>{selected.id}</code>
            </span>
          </div>

          <div className="scoreboard">
            <div className="score">
              <span className="score-value">{active}</span>
              <span className="score-label">active bookings</span>
            </div>
            <div className="score">
              <span className="score-value">{seatsHeld}</span>
              <span className="score-label">seats held</span>
            </div>
            <div className="score">
              <span className="score-value">{theirs.length}</span>
              <span className="score-label">bookings total</span>
            </div>
          </div>

          {theirs.length === 0 ? (
            <p className="empty">No bookings for this passenger.</p>
          ) : (
            <div className="table-scroll">
              <table className="table table-inner">
                <thead>
                  <tr>
                    <th>Itinerary</th>
                    <th>Legs</th>
                    <th>Status</th>
                    <th>Booked</th>
                  </tr>
                </thead>
                <tbody>
                  {theirs.map((b) => (
                    <tr key={b.id}>
                      <td className="mono">
                        {b.legs
                          .map((l) => {
                            const f = flightOf(l.flight_id);
                            return f ? `${f.origin}→${f.destination}` : "?";
                          })
                          .join("  ·  ")}
                      </td>
                      <td className="mono">
                        {b.legs.map((l, i) => (
                          <span key={l.id}>
                            {i > 0 && <span className="arrow"> → </span>}
                            <span
                              className={`badge ${
                                CONSUMING.has(l.status) ? "badge-open" : "badge-muted"
                              }`}
                            >
                              {flightOf(l.flight_id)?.flight_number ?? "?"} {l.fare_class}
                            </span>
                          </span>
                        ))}
                      </td>
                      <td>
                        <span
                          className={`badge ${
                            b.status === "CONFIRMED" ? "badge-open" : "badge-muted"
                          }`}
                        >
                          {b.status}
                        </span>
                      </td>
                      <td className="muted">{new Date(b.created_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
