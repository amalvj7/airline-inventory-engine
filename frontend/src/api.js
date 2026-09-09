const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export { BASE as apiBaseUrl };

/**
 * A failed API call. The backend returns one envelope for every error --
 * {"error": "<CODE>", "detail": "<message>"} -- so `code` is always available
 * to switch on, and `detail` is always safe to show a user.
 */
export class ApiError extends Error {
  constructor(status, body) {
    super(body?.detail ?? `Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = body?.error ?? null;
    this.body = body ?? {};
  }
}

/** FastAPI 422s carry a list of {loc, msg}; flatten it into one readable line. */
function flattenValidationError(body) {
  if (!Array.isArray(body?.detail)) return null;
  return body.detail
    .map((d) => `${(d.loc ?? []).filter((p) => p !== "body").join(".")}: ${d.msg}`)
    .join("; ");
}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
      ...options,
    });
  } catch (cause) {
    // fetch only rejects on network-level failures: unreachable, asleep, or CORS-blocked.
    throw new ApiError(
      0,
      { detail: "Could not reach the API. It may be waking up — try again in a moment." },
      { cause },
    );
  }

  const text = await res.text();
  const body = text ? JSON.parse(text) : null;

  if (!res.ok) {
    const flat = flattenValidationError(body);
    throw new ApiError(res.status, flat ? { error: "VALIDATION_ERROR", detail: flat } : body);
  }
  return body;
}

const post = (path, payload, headers) =>
  request(path, { method: "POST", body: JSON.stringify(payload ?? {}), headers });

export const api = {
  health: () => request("/health"),

  flights: () => request("/flights"),
  createFlight: (payload) => post("/flights", payload),
  setOverbooking: (flightId, factor) =>
    request(`/flights/${flightId}/overbooking`, {
      method: "PATCH",
      body: JSON.stringify({ overbooking_factor: String(factor) }),
    }),
  bump: (flightId) => post(`/flights/${flightId}/bump`),

  passengers: () => request("/passengers"),
  createPassenger: (payload) => post("/passengers", payload),

  bookings: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/bookings${qs ? `?${qs}` : ""}`);
  },
  book: (passengerId, flightIds, idempotencyKey) =>
    post(
      "/bookings",
      { passenger_id: passengerId, legs: flightIds.map((id) => ({ flight_id: id })) },
      idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    ),
  cancel: (bookingId) => post(`/bookings/${bookingId}/cancel`),

  reconciliation: () => request("/reconciliation"),

  /** payload is either {flight_id, clients} or {groups:[{flight_ids, clients}]} */
  race: (payload) => post("/demo/race", payload),
};
