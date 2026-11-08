// Thin fetch wrapper for the backend API. All calls go to same-origin /api/* (Next rewrites them),
// so the httpOnly session cookie is sent automatically.

export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const STATUS_CODES: Record<number, string> = {
  400: "bad_request",
  401: "unauthenticated",
  403: "forbidden",
  404: "not_found",
  409: "conflict",
  422: "validation_error",
  429: "rate_limited",
  500: "internal_error",
  502: "bad_gateway",
  503: "service_unavailable",
  504: "gateway_timeout",
};

export type ApiInit = RequestInit & { json?: unknown; redirectOn401?: boolean };

export async function apiFetch<T = unknown>(path: string, init: ApiInit = {}): Promise<T> {
  const { json, redirectOn401 = true, headers, ...rest } = init;
  const h = new Headers(headers);
  if (json !== undefined) h.set("content-type", "application/json");
  h.set("accept", "application/json");

  const res = await fetch(path, {
    ...rest,
    headers: h,
    credentials: "include",
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });

  if (res.status === 204) return undefined as T;

  const isJson = (res.headers.get("content-type") ?? "").includes("application/json");
  const body = isJson ? await res.json().catch(() => null) : null;

  if (!res.ok) {
    const env = body?.error;
    const err = new ApiError(
      res.status,
      env?.code ?? STATUS_CODES[res.status] ?? "http_error",
      env?.message ?? `Request failed (${res.status})`,
      env?.details,
    );
    if (res.status === 401 && redirectOn401 && !path.startsWith("/api/auth/") && typeof location !== "undefined") {
      const next = encodeURIComponent(`${location.pathname}${location.search}`);
      location.assign(`/login?next=${next}`);
    }
    throw err;
  }
  return body as T;
}

export const api = {
  get: <T>(path: string, init?: ApiInit) => apiFetch<T>(path, { ...init, method: "GET" }),
  post: <T>(path: string, json?: unknown, init?: ApiInit) =>
    apiFetch<T>(path, { ...init, method: "POST", json: json ?? {} }),
  patch: <T>(path: string, json: unknown, init?: ApiInit) => apiFetch<T>(path, { ...init, method: "PATCH", json }),
};

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}
