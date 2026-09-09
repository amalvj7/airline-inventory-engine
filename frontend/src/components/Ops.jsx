import { useState } from "react";
import { api } from "../api";
import { Feedback } from "./Feedback";

function Reconciliation() {
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function check() {
    setBusy(true);
    setError(null);
    try {
      setReport(await api.reconciliation());
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const drifted = report?.flights.filter((f) => !f.ok) ?? [];

  return (
    <section className="card">
      <h2>Reconciliation</h2>
      <p className="hint">
        Recounts every flight&apos;s consuming legs and compares them against the stored counter.
        Any mismatch is drift — a counter that no longer matches the booking records.
      </p>

      <button className="btn btn-primary" onClick={check} disabled={busy}>
        {busy ? "Checking…" : "Verify counters"}
      </button>

      <Feedback error={error} />

      {report && (
        <>
          <div className={`feedback ${report.ok ? "feedback-ok" : "feedback-error"}`}>
            <strong>{report.ok ? "PASS" : "DRIFT DETECTED"}</strong>
            <span>
              {report.flights.length} flights checked · {drifted.length} with drift
            </span>
          </div>
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Flight</th>
                  <th className="num">Stored</th>
                  <th className="num">Counted</th>
                  <th className="num">Drift</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {report.flights.map((f) => (
                  <tr key={f.flight_id}>
                    <td className="mono strong">{f.flight_number}</td>
                    <td className="num mono">{f.stored_booked}</td>
                    <td className="num mono">{f.expected_booked}</td>
                    <td className="num mono">{f.drift}</td>
                    <td>
                      <span className={`badge ${f.ok ? "badge-open" : "badge-oversold"}`}>
                        {f.ok ? "ok" : "drift"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

function AddFlight({ onChanged }) {
  const [form, setForm] = useState({
    flight_number: "",
    origin: "",
    destination: "",
    physical_capacity: 3,
    overbooking_factor: "0.0",
    hours_from_now: 6,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(null);
    const departure = new Date(Date.now() + Number(form.hours_from_now) * 3600_000);
    const arrival = new Date(departure.getTime() + 2 * 3600_000);
    try {
      const flight = await api.createFlight({
        flight_number: form.flight_number.trim().toUpperCase(),
        origin: form.origin.trim().toUpperCase(),
        destination: form.destination.trim().toUpperCase(),
        departure_time: departure.toISOString(),
        arrival_time: arrival.toISOString(),
        physical_capacity: Number(form.physical_capacity),
        overbooking_factor: String(form.overbooking_factor),
      });
      setSuccess(`${flight.flight_number} created — booking limit ${flight.inventory.booking_limit}`);
      setForm((f) => ({ ...f, flight_number: "", origin: "", destination: "" }));
      await onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>Add flight</h2>
      <form onSubmit={submit}>
        <div className="grid">
          <label className="field">
            <span>Flight number</span>
            <input value={form.flight_number} onChange={set("flight_number")} placeholder="AI601" required />
          </label>
          <label className="field">
            <span>Origin</span>
            <input value={form.origin} onChange={set("origin")} placeholder="BLR" minLength={3} maxLength={3} required />
          </label>
          <label className="field">
            <span>Destination</span>
            <input value={form.destination} onChange={set("destination")} placeholder="DEL" minLength={3} maxLength={3} required />
          </label>
          <label className="field">
            <span>Seats</span>
            <input type="number" min="1" value={form.physical_capacity} onChange={set("physical_capacity")} required />
          </label>
          <label className="field">
            <span>Overbooking factor (0–2)</span>
            <input type="number" min="0" max="2" step="0.1" value={form.overbooking_factor} onChange={set("overbooking_factor")} required />
          </label>
          <label className="field">
            <span>Departs in (hours)</span>
            <input type="number" min="1" value={form.hours_from_now} onChange={set("hours_from_now")} required />
          </label>
        </div>
        <button className="btn btn-primary" disabled={busy}>
          {busy ? "Creating…" : "Create flight"}
        </button>
      </form>
      <Feedback error={error} success={success} />
    </section>
  );
}

function AddPassenger({ onChanged }) {
  const [name, setName] = useState("");
  const [tier, setTier] = useState("STANDARD");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const p = await api.createPassenger({ name: name.trim(), tier });
      setSuccess(`${p.name} added`);
      setName("");
      await onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>Add passenger</h2>
      <p className="hint">Tier decides bump priority: PLATINUM is bumped last, STANDARD first.</p>
      <form onSubmit={submit}>
        <div className="grid">
          <label className="field">
            <span>Name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Meera Suresh" required />
          </label>
          <label className="field">
            <span>Tier</span>
            <select value={tier} onChange={(e) => setTier(e.target.value)}>
              <option>STANDARD</option>
              <option>GOLD</option>
              <option>PLATINUM</option>
            </select>
          </label>
        </div>
        <button className="btn btn-primary" disabled={busy}>
          {busy ? "Adding…" : "Add passenger"}
        </button>
      </form>
      <Feedback error={error} success={success} />
    </section>
  );
}

export { Reconciliation, AddFlight, AddPassenger };
