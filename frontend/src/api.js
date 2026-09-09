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

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
      ...options,
    });
  } catch (cause) {
    // fetch only rejects on network-level failures: the API is unreachable,
    // asleep, or the browser blocked the response for a CORS reason.
    throw new ApiError(0, { detail: "Could not reach the API. It may be waking up." }, { cause });
  }

  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, body);
  return body;
}

export const api = {
  health: () => request("/health"),
  flights: () => request("/flights"),
  passengers: () => request("/passengers"),
};
