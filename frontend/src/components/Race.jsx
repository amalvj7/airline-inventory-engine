import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Feedback } from "./Feedback";

const LAST_SEAT = "last-seat";
const SHARED_LEG = "shared-leg";

/** The tightest flight that still has a seat makes the sharpest demo. */
function tightest(flights) {
  const open = flights.filter((f) => f.inventory.remaining > 0);
  const pool = open.length > 0 ? open : flights;
  return pool.reduce((best, f) => (f.inventory.remaining < best.inventory.remaining ? f : best));
}

export function Race({ flights, onChanged }) {
  const [mode, setMode] = useState(LAST_SEAT);
  const [flightId, setFlightId] = useState("");
  const [clients, setClients] = useState(10);

  const [sharedId, setSharedId] = useState("");
  const [feederA, setFeederA] = useState("");
  const [feederB, setFeederB] = useState("");
  const [perSide, setPerSide] = useState(3);

  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  // feeders must land where the contested leg departs from
  const shared = flights.find((f) => f.id === sharedId);
  const feeders = useMemo(
    () => (shared ? flights.filter((f) => f.destination === shared.origin) : []),
    [flights, shared],
  );

  useEffect(() => {
    if (flights.length === 0) return;
    if (!flightId) setFlightId(tightest(flights).id);
    if (!sharedId) {
      // prefer a contested leg that actually has feeders arriving into it
      const candidates = flights.filter((f) =>
        flights.some((g) => g.destination === f.origin && g.id !== f.id),
      );
      setSharedId((candidates.length ? tightest(candidates) : tightest(flights)).id);
    }
  }, [flights, flightId, sharedId]);

  useEffect(() => {
    if (feeders.length === 0) return;
    if (!feeders.some((f) => f.id === feederA)) setFeederA(feeders[0]?.id ?? "");
    if (!feeders.some((f) => f.id === feederB)) setFeederB(feeders[1]?.id ?? feeders[0]?.id ?? "");
  }, [feeders, feederA, feederB]);

  const flight = flights.find((f) => f.id === flightId);
  const ready =
    mode === LAST_SEAT
      ? Boolean(flightId)
      : Boolean(sharedId && feederA && feederB && feederA !== feederB);

  async function run() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const payload =
        mode === LAST_SEAT
          ? { flight_id: flightId, clients: Number(clients) }
          : {
              groups: [
                { flight_ids: [feederA, sharedId], clients: Number(perSide) },
                { flight_ids: [feederB, sharedId], clients: Number(perSide) },
              ],
            };
      setResult(await api.race(payload));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
      await onChanged();
    }
  }

  return (
    <section className="card card-feature">
      <h2>Concurrency test</h2>

      <div className="tabs">
        <button
          className={`tab${mode === LAST_SEAT ? " tab-active" : ""}`}
          onClick={() => { setMode(LAST_SEAT); setResult(null); }}
        >
          Last seat
        </button>
        <button
          className={`tab${mode === SHARED_LEG ? " tab-active" : ""}`}
          onClick={() => { setMode(SHARED_LEG); setResult(null); }}
        >
          Shared leg
        </button>
      </div>

      <p className="hint">
        {mode === LAST_SEAT ? (
          <>
            Fires {clients} clients at one flight <strong>simultaneously</strong> — real threads on
            independent connections, released together by a barrier. Exactly the remaining seats
            should be sold, and no more.
          </>
        ) : (
          <>
            Two different itineraries compete for one seat on the leg they <strong>share</strong>.
            The loser must end up holding <strong>nothing</strong> — not even its own uncontested
            first leg — because a multi-leg booking is claimed all-or-nothing.
          </>
        )}
      </p>

      {mode === LAST_SEAT ? (
        <div className="race-controls">
          <label className="field">
            <span>Flight</span>
            <select value={flightId} onChange={(e) => setFlightId(e.target.value)}>
              {flights.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.flight_number} · {f.origin}→{f.destination} · {f.inventory.remaining} of{" "}
                  {f.inventory.booking_limit} left
                </option>
              ))}
            </select>
          </label>
          <label className="field field-narrow">
            <span>Clients</span>
            <input type="number" min="2" max="20" value={clients}
              onChange={(e) => setClients(e.target.value)} />
          </label>
          <button className="btn btn-primary btn-race" onClick={run} disabled={busy || !ready}>
            {busy ? "Racing…" : `Run ${clients} at once`}
          </button>
        </div>
      ) : (
        <>
          <div className="race-controls">
            <label className="field">
              <span>Contested leg</span>
              <select value={sharedId} onChange={(e) => setSharedId(e.target.value)}>
                {flights.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.flight_number} · {f.origin}→{f.destination} · {f.inventory.remaining} left
                  </option>
                ))}
              </select>
            </label>
            <label className="field field-narrow">
              <span>Per side</span>
              <input type="number" min="1" max="10" value={perSide}
                onChange={(e) => setPerSide(e.target.value)} />
            </label>
          </div>
          <div className="race-controls">
            <label className="field">
              <span>Itinerary A feeder</span>
              <select value={feederA} onChange={(e) => setFeederA(e.target.value)}>
                {feeders.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.flight_number} · {f.origin}→{f.destination}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Itinerary B feeder</span>
              <select value={feederB} onChange={(e) => setFeederB(e.target.value)}>
                {feeders.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.flight_number} · {f.origin}→{f.destination}
                  </option>
                ))}
              </select>
            </label>
            <button className="btn btn-primary btn-race" onClick={run} disabled={busy || !ready}>
              {busy ? "Racing…" : `Run ${perSide * 2} at once`}
            </button>
          </div>
          {feeders.length < 2 && (
            <p className="hint hint-warn">
              Only {feeders.length} flight(s) arrive into {shared?.origin}. Pick a contested leg
              with at least two feeders for a true shared-leg race.
            </p>
          )}
          {feederA === feederB && feeders.length > 1 && (
            <p className="hint hint-warn">Pick two different feeder flights.</p>
          )}
        </>
      )}

      {mode === LAST_SEAT && flight && !result && !busy && (
        <p className="hint">
          {flight.flight_number} has <strong>{Math.max(flight.inventory.remaining, 0)}</strong> seat
          {flight.inventory.remaining === 1 ? "" : "s"} left, so exactly that many of the {clients}{" "}
          attempts should succeed.
        </p>
      )}

      <Feedback error={error} />

      {result && (
        <>
          <div className="scoreboard">
            <div className="score score-ok">
              <span className="score-value">{result.accepted}</span>
              <span className="score-label">accepted</span>
            </div>
            <div className="score score-rejected">
              <span className="score-value">{result.rejected}</span>
              <span className="score-label">rejected</span>
            </div>
            {result.failed > 0 && (
              <div className="score score-failed">
                <span className="score-value">{result.failed}</span>
                <span className="score-label">errored</span>
              </div>
            )}
            <div className="score">
              <span className="score-value">{result.elapsed_ms}</span>
              <span className="score-label">ms</span>
            </div>
          </div>

          {result.groups.length > 1 && (
            <table className="table">
              <thead>
                <tr>
                  <th>Itinerary</th>
                  <th className="num">Clients</th>
                  <th className="num">Accepted</th>
                  <th className="num">Rejected</th>
                </tr>
              </thead>
              <tbody>
                {result.groups.map((g) => (
                  <tr key={g.label}>
                    <td className="mono strong">{g.label}</td>
                    <td className="num mono">{g.clients}</td>
                    <td className="num mono">{g.accepted}</td>
                    <td className="num mono">{g.rejected}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <table className="table">
            <thead>
              <tr>
                <th>Flight</th>
                <th className="num">Limit</th>
                <th className="num">Booked before</th>
                <th className="num">Booked after</th>
                <th className="num">Claimed</th>
              </tr>
            </thead>
            <tbody>
              {result.flights.map((f) => (
                <tr key={f.flight_id}>
                  <td className="mono strong">{f.flight_number}</td>
                  <td className="num mono">{f.after.booking_limit}</td>
                  <td className="num mono muted">{f.before.booked_count}</td>
                  <td className="num mono strong">{f.after.booked_count}</td>
                  <td className="num mono">{f.seats_claimed >= 0 ? `+${f.seats_claimed}` : f.seats_claimed}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className={`feedback ${result.within_limit && result.consistent ? "feedback-ok" : "feedback-error"}`}>
            <strong>
              {result.within_limit && result.consistent ? "NO OVERSELL" : "INVARIANT VIOLATED"}
            </strong>
            <span>
              {result.clients} clients competed · {result.accepted} booking
              {result.accepted === 1 ? "" : "s"} confirmed · {result.seats_claimed} seat
              {result.seats_claimed === 1 ? "" : "s"} claimed across{" "}
              {result.flights.length} flight{result.flights.length === 1 ? "" : "s"}
              {result.consistent
                ? ` — exactly the ${result.seats_expected} expected`
                : ` — expected ${result.seats_expected}`}
              . Every flight stayed within its booking limit
              {result.within_limit ? "." : " — IT DID NOT."}
            </span>
          </div>

          {result.errors.length > 0 && (
            <div className="feedback feedback-error">
              <strong>UNEXPECTED</strong>
              <span>{result.errors.join(" · ")}</span>
            </div>
          )}
        </>
      )}
    </section>
  );
}
