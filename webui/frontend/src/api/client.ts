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
  patch: <T extends ApiEnvelope = ApiEnvelope>(
    path: string,
    opts?: RequestOptions,
  ) => request<T>("PATCH", path, opts),
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

// ── Top Picks ─────────────────────────────────────────────────────────────────
/** An inbox row as ranked into the Top Picks shortlist. Engine columns pass
 * through as-is (serializers.inbox_row); we type the fields the tab reads and
 * keep an index signature for the rest (extras, score_notes, dates, …). */
export interface TopPickRow {
  id: number;
  rank: number;
  title: string;
  company: string;
  location: string;
  url: string;
  /** Base match score (0–100) or -1/absent when unscored. */
  score?: number | null;
  /** AI re-rank fit (0–100) or -1/absent when not fit-scored. */
  fit?: number | null;
  /** One-line AI rationale for the fit (may be empty). */
  fit_why?: string | null;
  source?: string | null;
  extras?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface TopPicksResponse extends ApiEnvelope {
  rows: TopPickRow[];
}

/** `limit` maps to the engine's top_picks(limit): "all" | 0 = every ranked row. */
export type TopPicksLimit = number | "all";

export interface TrackResponse extends ApiEnvelope {
  app_id: number;
}

// ── Source keys ───────────────────────────────────────────────────────────────
export interface SourceField {
  name: string;
  label: string;
  set: boolean;
  /** Last-4 mask (e.g. "••••1234") when set; null when unset. Never the raw value. */
  masked: string | null;
}

export interface SourceKeyInfo {
  id: string;
  label: string;
  fields: SourceField[];
  get_key_url: string;
  impact: string;
}

export interface SourceKeysResponse extends ApiEnvelope {
  sources: SourceKeyInfo[];
}

export interface SourceKeyPutResponse extends ApiEnvelope {
  saved: string[];
  warnings: { field: string; warning: string }[];
}

export interface SourceTestResponse extends ApiEnvelope {
  result: { status: "ok" | "failed"; detail: string };
}

export interface AdzunaSplitResponse extends ApiEnvelope {
  app_id?: string;
  app_key?: string;
}

// ── Applications (Tracker + Board + JobDialog) ────────────────────────────────
/** A tracked-application row (serializers.app_row) — engine columns pass through
 * as-is. We type the fields the UI reads and keep an index signature for the rest
 * (offer_*, contact, timestamps a future column adds). */
export interface AppRow {
  id: number;
  title: string;
  company: string;
  location?: string | null;
  salary_text?: string | null;
  url?: string | null;
  status: string;
  date_applied?: string | null;
  date_added?: string | null;
  follow_up_date?: string | null;
  deadline?: string | null;
  contact?: string | null;
  notes?: string | null;
  source?: string | null;
  archived?: number | boolean | null;
  offer_amount?: string | null;
  offer_deadline?: string | null;
  offer_notes?: string | null;
  [key: string]: unknown;
}

/** Funnel counts keyed by status, plus the synthetic `all` / `archived` totals. */
export type AppCounts = Record<string, number>;

export interface AppListResponse extends ApiEnvelope {
  rows: AppRow[];
  counts: AppCounts;
  followups_due: number;
}

/** A status-history / note timeline entry (service.status_timeline). */
export interface TimelineEntry {
  old_status?: string | null;
  new_status?: string | null;
  changed_at: string | null;
  note?: string | null;
  /** "status" for a transition, "note" for a standalone note. */
  kind: "status" | "note";
  [key: string]: unknown;
}

/** An interview round row (service.list_interview_rounds). */
export interface InterviewRound {
  id: number;
  app_id: number;
  round_no: number;
  kind: string;
  scheduled_at?: string | null;
  interviewer?: string | null;
  notes?: string | null;
  outcome?: string | null;
  [key: string]: unknown;
}

/** The one-call JobDialog payload (GET /api/applications/<id>). */
export interface AppDetailResponse extends ApiEnvelope {
  job: AppRow;
  timeline: TimelineEntry[];
  rounds: InterviewRound[];
  /** "" when no known contact at the company. */
  referral: string;
  statuses: string[];
  status_labels: Record<string, string>;
}

export interface AddAppResponse extends ApiEnvelope {
  id: number;
}

export interface AppMutationResponse extends ApiEnvelope {
  job: AppRow;
}

export interface NotesResponse extends ApiEnvelope {
  timeline: TimelineEntry[];
}

export interface RoundsResponse extends ApiEnvelope {
  rounds: InterviewRound[];
  id?: number;
}

/** A board card = an app row + the funnel augmentation the /board route adds. */
export interface BoardCardRow extends AppRow {
  days_in_stage: number | null;
  days_label: string;
  forward_targets: string[];
}

export interface BoardColumn {
  status: string;
  label: string;
  cards: BoardCardRow[];
}

export interface BoardResponse extends ApiEnvelope {
  columns: BoardColumn[];
}

/** Fields the add/edit endpoints accept (a Partial keeps the wrappers honest
 * without re-listing the whole column set). */
export type AppFields = Partial<Record<string, string>>;
export type RoundFields = Partial<Record<string, string | number>>;

/** Named endpoint wrappers for the shell + Phase 1 tabs. Phase 1+ extends this. */
export const endpoints = {
  status: () => api.get<StatusResponse>("/status"),
  projects: () => api.get<ProjectListResponse>("/project"),
  switchProject: (slug: string) =>
    api.post<ProjectListResponse>("/project", { json: { slug } }),
  getTheme: () => api.get<ThemeResponse>("/settings/theme"),
  setTheme: (mode: ThemeMode) =>
    api.put<ThemeResponse>("/settings/theme", { json: { mode } }),

  // Top Picks
  topPicks: (limit: TopPicksLimit) =>
    api.get<TopPicksResponse>("/toppicks", { params: { limit } }),
  trackInbox: (inboxId: number) =>
    api.post<TrackResponse>(`/inbox/${inboxId}/track`),
  dismissInbox: (inboxId: number) =>
    api.post<ApiEnvelope>(`/inbox/${inboxId}/dismiss`),

  // Source keys
  sourceKeys: () => api.get<SourceKeysResponse>("/settings/keys"),
  saveSourceKey: (source: string, fields: Record<string, string>) =>
    api.put<SourceKeyPutResponse>(`/settings/keys/${source}`, { json: fields }),
  testSourceKey: (source: string) =>
    api.post<SourceTestResponse>(`/settings/keys/${source}/test`),
  splitAdzuna: (clipboard: string) =>
    api.post<AdzunaSplitResponse>("/settings/keys/adzuna/split", {
      json: { clipboard },
    }),

  // ── Applications (Tracker + Board + JobDialog) ──────────────────────────────
  listApplications: (status?: string) =>
    api.get<AppListResponse>("/applications", {
      params: status ? { status } : undefined,
    }),
  getApplication: (id: number) =>
    api.get<AppDetailResponse>(`/applications/${id}`),
  addApplication: (fields: AppFields) =>
    api.post<AddAppResponse>("/applications", { json: fields }),
  updateApplication: (id: number, fields: AppFields) =>
    api.patch<AppMutationResponse>(`/applications/${id}`, { json: fields }),
  setApplicationStatus: (id: number, status: string) =>
    api.post<AppMutationResponse>(`/applications/${id}/status`, {
      json: { status },
    }),
  archiveApplication: (id: number) =>
    api.post<ApiEnvelope>(`/applications/${id}/archive`),
  restoreApplication: (id: number) =>
    api.post<ApiEnvelope>(`/applications/${id}/restore`),
  deleteApplication: (id: number) =>
    api.del<ApiEnvelope>(`/applications/${id}`),
  addAppNote: (id: number, note: string) =>
    api.post<NotesResponse>(`/applications/${id}/notes`, { json: { note } }),
  addRound: (id: number, fields: RoundFields) =>
    api.post<RoundsResponse>(`/applications/${id}/rounds`, { json: fields }),
  updateRound: (id: number, rid: number, fields: RoundFields) =>
    api.patch<RoundsResponse>(`/applications/${id}/rounds/${rid}`, {
      json: fields,
    }),
  deleteRound: (id: number, rid: number) =>
    api.del<RoundsResponse>(`/applications/${id}/rounds/${rid}`),

  // Board
  board: () => api.get<BoardResponse>("/board"),

  // ── Inbox (flagship — Phase 3) ──────────────────────────────────────────────
  inbox: (params: Record<string, string | number | boolean | undefined>) =>
    api.get<InboxListResponse>("/inbox", { params }),
  inboxDetail: (id: number) =>
    api.get<InboxDetailResponse>(`/inbox/${id}/detail`),
  dismissBulk: (ids: number[]) =>
    api.post<DismissBulkResponse>("/inbox/dismiss-bulk", { json: { ids } }),
  undoDismiss: (undoToken?: string) =>
    api.post<UndoDismissResponse>("/inbox/undo-dismiss", {
      json: undoToken ? { undo_token: undoToken } : {},
    }),
  undoRerank: () => api.post<UndoRerankResponse>("/inbox/undo-rerank"),
  exportInbox: (args: ExportArgs) =>
    api.post<InboxExportResponse>("/inbox/export", { json: args }),
  scoreReply: (text: string) =>
    api.post<ScoreReplyResponse>("/inbox/score-reply", { json: { text } }),

  // Runs / jobs
  startDailyRun: () => api.post<StartRunResponse>("/runs/daily"),
  // The job snapshot's `error` is `string | null` (an explicit null while
  // running), which doesn't fit ApiEnvelope's `error?: string`, so we fetch the
  // base envelope and cast to the richer shape rather than loosen ApiEnvelope.
  jobStatus: (jobId: string) =>
    api
      .get<ApiEnvelope & { [k: string]: unknown }>(`/jobs/${jobId}`)
      .then((r) => r as unknown as JobStatusResponse),
  cancelJob: (jobId: string) =>
    api.post<CancelJobResponse>(`/jobs/${jobId}/cancel`),
};

/** Import AI scores — multipart (file) OR JSON (pasted text). We build the
 * request by hand (the JSON client can't send multipart) but still unwrap the
 * {ok,...} envelope into ApiError on failure, matching the rest of the client. */
export async function importInbox(
  input: { file: File } | { text: string },
  policy: ImportPolicy,
): Promise<InboxImportResponse> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Requested-With": "zaggregate-webui",
  };
  let init: RequestInit;
  if ("file" in input) {
    const fd = new FormData();
    fd.append("file", input.file);
    fd.append("policy", policy);
    init = { method: "POST", headers, body: fd };
  } else {
    headers["Content-Type"] = "application/json";
    init = {
      method: "POST",
      headers,
      body: JSON.stringify({ text: input.text, policy }),
    };
  }
  let resp: Response;
  try {
    resp = await fetch("/api/inbox/import", init);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "network error";
    throw new ApiError(msg, 0, null);
  }
  let body: unknown = null;
  const ctype = resp.headers.get("content-type") ?? "";
  if (ctype.includes("application/json")) {
    body = await resp.json().catch(() => null);
  }
  const envelope = (body ?? {}) as ApiEnvelope;
  if (!resp.ok || envelope.ok === false) {
    const message =
      envelope.error || `Import failed (${resp.status} ${resp.statusText})`;
    throw new ApiError(message, resp.status, body);
  }
  return body as InboxImportResponse;
}

/** Trigger a browser download of an exported AI file. The route serves it as an
 * attachment locked to the export dir; we fetch → blob → object-URL → click a
 * hidden <a> so nothing shells out to the OS (repo rule: HTTP downloads only). */
export async function downloadExport(
  downloadUrl: string,
  filename: string,
): Promise<void> {
  let resp: Response;
  try {
    resp = await fetch(downloadUrl);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "network error";
    throw new ApiError(msg, 0, null);
  }
  const ctype = resp.headers.get("content-type") ?? "";
  if (!resp.ok || ctype.includes("application/json")) {
    let message = `Download failed (${resp.status})`;
    if (ctype.includes("application/json")) {
      const b = (await resp.json().catch(() => null)) as ApiEnvelope | null;
      if (b?.error) message = b.error;
    }
    throw new ApiError(message, resp.status, null);
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ── Inbox (flagship — Phase 3) ────────────────────────────────────────────────
/** Cheap per-row computed fields the list route adds (webui/api/inbox.py::_computed). */
export interface InboxComputed {
  is_new: boolean;
  /** Company-size letter S/M/L/XL/? from board_count. */
  size: string;
  /** Whether the row passes the requested Location mode (false = out-of-area). */
  location_visible: boolean;
}

/** A serialized inbox row + its computed block. Engine columns pass through as-is
 * (serializers.inbox_row); we type the fields the table reads and keep an index
 * signature for the rest (score_notes, board_count, job_key, …). */
export interface InboxRow {
  id: number;
  title: string;
  company: string;
  location: string;
  url: string;
  salary_text?: string | null;
  source?: string | null;
  /** Base match score (0–100) or -1/absent when unscored. */
  score?: number | null;
  /** AI re-rank fit (0–100) or -1/absent when not fit-scored. */
  fit?: number | null;
  fit_why?: string | null;
  /** Posting timestamp (ISO-ish) — falls back to date_added in the engine sort. */
  created?: string | null;
  date_added?: string | null;
  board_count?: number | null;
  extras?: Record<string, unknown>;
  computed: InboxComputed;
  [key: string]: unknown;
}

/** Header badges: last-run summary, reach line, demo flag (inbox.py::_badges). */
export interface InboxBadges {
  last_run: {
    timestamp: string | null;
    added: number;
    keyless_skipped: string[];
  } | null;
  reach: { line: string; reason: string } | null;
  demo: boolean;
}

export interface InboxListResponse extends ApiEnvelope {
  rows: InboxRow[];
  /** Pre-filter inbox size (M in "N of M"). */
  total: number;
  /** Post-filter, pre-paging count. */
  shown: number;
  badges: InboxBadges;
}

/** The detail-pane payload (inbox.py::inbox_detail). */
export interface InboxDetailResponse extends ApiEnvelope {
  row: InboxRow;
  fit_why: string;
  /** Score breakdown dict (label → contribution / note). */
  score_notes: Record<string, unknown>;
  /** Ghost/staleness verdict ({level, ...}) — may be empty. */
  ghost: Record<string, unknown>;
  ats: {
    ats: string;
    matched: string[];
    missing: string[];
    have: number;
    lines: string[];
  };
  description_preview: string;
}

export interface DismissBulkResponse extends ApiEnvelope {
  dismissed: number;
  undo_token?: string;
}

export interface UndoDismissResponse extends ApiEnvelope {
  restored: number;
}

export interface UndoRerankResponse extends ApiEnvelope {
  restored: number;
}

export type ExportScope = "all" | "view";
export type ExportFmt = "both" | "csv" | "md";

export interface ExportFile {
  name: string;
  download_url: string;
}

export interface InboxExportResponse extends ApiEnvelope {
  files: ExportFile[];
  count: number;
}

export type ImportPolicy = "overwrite" | "keep_existing" | "add_only";

export interface ImportResult {
  matched: number;
  updated: number;
  unmatched: number;
  skipped: number;
  errors: string[];
}

export interface InboxImportResponse extends ApiEnvelope {
  result: ImportResult;
}

export interface ScoreReplyResponse extends ApiEnvelope {
  applied: number;
  asked: number;
  missed: number;
}

// ── Runs / jobs (daily run + SSE) ─────────────────────────────────────────────
export interface StartRunResponse extends ApiEnvelope {
  job_id: string;
}

/** 409 body shape carried on ApiError.body when a run is already in flight. */
export interface RunConflictBody {
  ok: false;
  error: string;
  job_id: string;
}

export type JobStatus = "running" | "done" | "failed" | "cancelled";

/** The job status snapshot (webui/jobs.py::_Job.snapshot). `error` is an explicit
 * `null` while running (not undefined), so this is a standalone shape rather than
 * an ApiEnvelope extension; `endpoints.jobStatus` fetches the base envelope and
 * casts to this. The JSON client still throws ApiError on a non-2xx / ok:false. */
export interface JobStatusResponse {
  ok: boolean;
  status: JobStatus;
  lines_tail: string[];
  result: unknown;
  /** The failure message on a failed job; null while running / on success. */
  error: string | null;
}

export interface CancelJobResponse extends ApiEnvelope {
  cancelled: boolean;
}

/** The filter payload the export route re-applies server-side for scope='view'.
 * Mirrors the GET /api/inbox param names (snake_case), NOT the frontend camelCase
 * state — the caller maps state → this shape at the call site. */
export interface ExportViewFilters {
  min_score?: number | null;
  sources?: string[];
  size?: string | null;
  location_mode?: string | null;
  pay_floor?: boolean;
  q?: string | null;
  new_only?: boolean;
  unscored_only?: boolean;
  hide_stale?: boolean;
}

export interface ExportArgs {
  scope: ExportScope;
  fmt?: ExportFmt;
  compact?: boolean;
  chunk_size?: number;
  filters?: ExportViewFilters;
}

/** SSE endpoint (relative to /api) for a job's live event stream. Consumed via a
 * native EventSource in the Inbox run console, NOT the JSON client. */
export function jobEventsUrl(jobId: string): string {
  return `/api/jobs/${encodeURIComponent(jobId)}/events`;
}

/** Path (relative to /api) for a round's .ics — used by downloadIcs, NOT fetched
 * through the JSON client (the response is text/calendar). */
export function roundIcsUrl(id: number, rid: number): string {
  return `/api/applications/${id}/rounds/${rid}/ics`;
}

/** Trigger a browser download of a round's .ics. The route streams a
 * Content-Disposition: attachment file; a 400 (no scheduled_at) or 404 returns a
 * JSON error, which we surface as a thrown ApiError so the caller can toast it.
 * We fetch → blob → object-URL → click a hidden <a> so the filename the server
 * set is honored and nothing shells out to the OS (repo rule: HTTP downloads
 * only). */
export async function downloadIcs(id: number, rid: number): Promise<void> {
  let resp: Response;
  try {
    resp = await fetch(roundIcsUrl(id, rid), {
      headers: { Accept: "text/calendar" },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "network error";
    throw new ApiError(msg, 0, null);
  }
  const ctype = resp.headers.get("content-type") ?? "";
  if (!resp.ok || ctype.includes("application/json")) {
    let message = `Request failed (${resp.status})`;
    if (ctype.includes("application/json")) {
      const body = (await resp.json().catch(() => null)) as ApiEnvelope | null;
      if (body?.error) message = body.error;
    }
    throw new ApiError(message, resp.status, null);
  }
  const blob = await resp.blob();
  // Prefer the server's filename from Content-Disposition; fall back to a slug.
  const disp = resp.headers.get("content-disposition") ?? "";
  const match = /filename="?([^"]+)"?/i.exec(disp);
  const filename = match?.[1] ?? `interview-r${rid}.ics`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
