import { useState } from "react";
import { api } from "../api";
import { Feedback } from "./Feedback";

const EMPTY = "";

export function BookSeat({ flights, passengers, onChanged }) {
  const [passengerId, setPassengerId] = useState(EMPTY);
  const [legs, setLegs] = useState([EMPTY]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const chosen = legs.filter(Boolean);
  const duplicate = new Set(chosen).size !== chosen.length;
  const canSubmit = passengerId && chosen.length > 0 && !duplicate && !busy;

  function setLeg(index, value) {
    setLegs((current) => current.map((leg, i) => (i === index ? value : leg)));
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const booking = await api.book(passengerId, chosen);
      const route = booking.legs
        .map((leg) => flights.find((f) => f.id === leg.flight_id)?.flight_number ?? "?")
        .join(" → ");
      setSuccess(`Booked ${route} — ${booking.status}`);
      setLegs([EMPTY]);
      await onChanged();
    } catch (err) {
      setError(err);
      await onChanged(); // a rejected booking still means the counters moved elsewhere
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>Book a seat</h2>
      <p className="hint">
        Add more than one leg to build a connecting itinerary. It is claimed all-or-nothing: if
        any leg is full the whole booking is rejected and nothing is held.
      </p>

      <form onSubmit={submit}>
        <label className="field">
          <span>Passenger</span>
          <select value={passengerId} onChange={(e) => setPassengerId(e.target.value)}>
            <option value={EMPTY}>Select a passenger…</option>
            {passengers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} · {p.tier}
              </option>
            ))}
          </select>
        </label>

        {legs.map((leg, index) => (
          <label className="field" key={index}>
            <span>Leg {index + 1}</span>
            <div className="field-row">
              <select value={leg} onChange={(e) => setLeg(index, e.target.value)}>
                <option value={EMPTY}>Select a flight…</option>
                {flights.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.flight_number} · {f.origin}→{f.destination} · {f.inventory.remaining} left
                  </option>
                ))}
              </select>
              {legs.length > 1 && (
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() => setLegs((c) => c.filter((_, i) => i !== index))}
                >
                  Remove
                </button>
              )}
            </div>
          </label>
        ))}

        {duplicate && (
          <p className="hint hint-warn">
            The same flight appears twice — an itinerary cannot use one flight for two legs.
          </p>
        )}

        <div className="actions">
          <button type="button" className="btn btn-sm" onClick={() => setLegs((c) => [...c, EMPTY])}>
            + Add leg
          </button>
          <button type="submit" className="btn btn-primary" disabled={!canSubmit}>
            {busy ? "Booking…" : "Book"}
          </button>
        </div>
      </form>

      <Feedback error={error} success={success} />
    </section>
  );
}
