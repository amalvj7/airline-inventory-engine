import { useCallback, useEffect, useState } from "react";
import { api, apiBaseUrl } from "./api";
import { BookSeat } from "./components/BookSeat";
import { Bookings } from "./components/Bookings";
import { Feedback } from "./components/Feedback";
import { Flights } from "./components/Flights";
import { AddFlight, AddPassenger, Reconciliation } from "./components/Ops";

export default function App() {
  const [flights, setFlights] = useState([]);
  const [passengers, setPassengers] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadedAt, setLoadedAt] = useState(null);

  /** One refresh for the whole page: any action re-reads all three lists, so
   *  inventory visibly moves the moment a booking succeeds or is cancelled. */
  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [f, p, b] = await Promise.all([api.flights(), api.passengers(), api.bookings()]);
      setFlights(f);
      setPassengers(p);
      setBookings(b);
      setLoadedAt(new Date());
    } catch (err) {
      setError(err);
    }
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  const ready = flights.length > 0;

  return (
    <div className="page">
      <header className="header">
        <div>
          <h1>Airline Seat Inventory</h1>
          <p className="subtitle">
            <code>{apiBaseUrl}</code>
            {loadedAt && <> · updated {loadedAt.toLocaleTimeString()}</>}
          </p>
        </div>
        <button className="btn" onClick={refresh} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </header>

      <Feedback error={error} />

      {loading && !ready && (
        <div className="feedback">
          Contacting the API… the first request after a while can take up to a minute while the
          free instance wakes up.
        </div>
      )}

      {ready && (
        <>
          <Flights flights={flights} onChanged={refresh} />

          <div className="columns">
            <BookSeat flights={flights} passengers={passengers} onChanged={refresh} />
            <Bookings
              bookings={bookings}
              flights={flights}
              passengers={passengers}
              onChanged={refresh}
            />
          </div>

          <Reconciliation />

          <div className="columns">
            <AddFlight onChanged={refresh} />
            <AddPassenger onChanged={refresh} />
          </div>
        </>
      )}
    </div>
  );
}
