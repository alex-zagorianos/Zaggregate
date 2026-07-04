/* Typed fetch wrapper for the Zaggregate JSON API (webui/api/*).
 *
 * Every backend response is a `{ ok: true, ... }` / `{ ok: false, error }`
 * envelope with a matching HTTP status (see the API contract in
 * brain/plan-2026-07-04-webui-migration.md). This client unwraps that envelope:
 * on `ok:false` OR a non-2xx status it throws `ApiError` (so callers / TanStack
 * Query treat it as a rejected promise); on success it returns the parsed JSON
 * (still including `ok:true`, so callers can read sibling fields directly).
 *
 * Mutating requests (POST/PUT/DELETE) are relative `/api/*` paths, so they go
 * to whatever origin served the page — same-origin by construction, which
 * satisfies the receiver's _origin_allowed() loopback gate. We send JSON bodies
 * and `X-Requested-With` so the server can distinguish app calls if needed.
 *
 * Phase 1+ builders: add typed endpoint wrappers to src/api/endpoints.ts (create
 * it) that call `api.get`/`api.post`/etc. and type the return — do NOT scatter
 * raw fetch() calls through components. Pair each wrapper with a TanStack Query
 * key in src/api/queries.ts.
 */

/** Shape shared by every API response. */
export interface ApiEnvelope {
  ok: boolean;
  error?: string;
}

/** Thrown on transport failure, non-2xx status, or an `ok:false` envelope. */
export class ApiError extends Error {
  readonly status: number;
  /** The parsed response body when there was one (may hold extra fields). */
  readonly body: unknown;
  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

type Method = "GET" | "POST" | "PUT" | "DELETE" | "PATCH";

interface RequestOptions {
  /** JSON body for mutating requests. */
  json?: unknown;
  /** Extra query params (undefined/null values are dropped). */
  params?: Record<string, string | number | boolean | undefined | null>;
  /** Passed through to fetch (e.g. an AbortSignal). */
  signal?: AbortSignal;
}

function buildUrl(path: string, params?: RequestOptions["params"]): string {
  const base = path.startsWith("/api") ? path : `/api${path}`;
  if (!params) return base;
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") usp.set(k, String(v));
  }
  const qs = usp.toString();
  return qs ? `${base}?${qs}` : base;
}

async function request<T extends ApiEnvelope = ApiEnvelope>(
  method: Method,
  path: string,
  opts: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Requested-With": "zaggregate-webui",
  };
  const init: RequestInit = { method, headers, signal: opts.signal };
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(opts.json);
  }

  let resp: Response;
  try {
    resp = await fetch(buildUrl(path, opts.params), init);
  } catch (e) {
    // Network / abort / server-down — normalize to ApiError so callers have one
    // failure type to handle.
    const msg = e instanceof Error ? e.message : "network error";
    throw new ApiError(msg, 0, null);
  }

  // Some endpoints (downloads) won't be JSON, but every /api/* route in the
  // contract returns JSON; parse defensively.
  let body: unknown = null;
  const ctype = resp.headers.get("content-type") ?? "";
  if (ctype.includes("application/json")) {
    body = await resp.json().catch(() => null);
  }

  const envelope = (body ?? {}) as ApiEnvelope;
  if (!resp.ok || envelope.ok === false) {
    const message =
      envelope.error || `Request failed (${resp.status} ${resp.statusText})`;
    throw new ApiError(message, resp.status, body);
  }
  return body as T;
}

export const api = {
  get: <T extends ApiEnvelope = ApiEnvelope>(
    path: string,
    opts?: Omit<RequestOptions, "json">,
  ) => request<T>("GET", path, opts),
  post: <T extends ApiEnvelope = ApiEnvelope>(
    path: string,
    opts?: RequestOptions,
  ) => request<T>("POST", path, opts),
  put: <T extends ApiEnvelope = ApiEnvelope>(
    path: string,
    opts?: RequestOptions,
  ) => request<T>("PUT", path, opts),
  del: <T extends ApiEnvelope = ApiEnvelope>(
    path: string,
    opts?: RequestOptions,
  ) => request<T>("DELETE", path, opts),
};

// ── Typed responses for the Phase 0b endpoints the shell consumes ─────────────
export interface StatusResponse extends ApiEnvelope {
  version: string;
  project: string;
  theme: ThemeMode;
}

export interface ProjectSummary {
  slug: string;
  name: string;
  person: string | null;
  daily: boolean;
}

export interface ProjectListResponse extends ApiEnvelope {
  active: string;
  projects: ProjectSummary[];
}

export type ThemeMode = "light" | "dark";

export interface ThemeResponse extends ApiEnvelope {
  mode: ThemeMode;
}

/** Named endpoint wrappers for the shell. Phase 1+ extends this surface. */
export const endpoints = {
  status: () => api.get<StatusResponse>("/status"),
  projects: () => api.get<ProjectListResponse>("/project"),
  switchProject: (slug: string) =>
    api.post<ProjectListResponse>("/project", { json: { slug } }),
  getTheme: () => api.get<ThemeResponse>("/settings/theme"),
  setTheme: (mode: ThemeMode) =>
    api.put<ThemeResponse>("/settings/theme", { json: { mode } }),
};
