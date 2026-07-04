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
  // Optional run-shaping knobs (S36 parity gap P1): max_pages 1–10 caps the
  // per-keyword pagination (CLI --max-pages, engine default 2); min_score
  // 0–100 is the inbox threshold (CLI --min-score). Omitted -> engine defaults.
  startDailyRun: (knobs?: DailyRunKnobs) =>
    api.post<StartRunResponse>(
      "/runs/daily",
      knobs && Object.keys(knobs).length ? { json: knobs } : undefined,
    ),
  // The job snapshot's `error` is `string | null` (an explicit null while
  // running), which doesn't fit ApiEnvelope's `error?: string`, so we fetch the
  // base envelope and cast to the richer shape rather than loosen ApiEnvelope.
  jobStatus: (jobId: string) =>
    api
      .get<ApiEnvelope & { [k: string]: unknown }>(`/jobs/${jobId}`)
      .then((r) => r as unknown as JobStatusResponse),
  cancelJob: (jobId: string) =>
    api.post<CancelJobResponse>(`/jobs/${jobId}/cancel`),

  // ── Search (Phase 4) ────────────────────────────────────────────────────────
  startSearch: (args: SearchArgs) =>
    api.post<StartRunResponse>("/search", { json: args }),
  // The search result rides on the generic job snapshot (GET /api/jobs/<id>); the
  // {rows, health} live under `.result`. We fetch the base envelope and cast, same
  // as jobStatus, then read result off it.
  searchResult: (jobId: string) =>
    api
      .get<ApiEnvelope & { [k: string]: unknown }>(`/jobs/${jobId}`)
      .then((r) => r as unknown as SearchJobSnapshot),
  trackSearchRow: (row: SearchRow) =>
    api.post<TrackSearchResponse>("/search/track", { json: { row } }),
  dismissSearchUrl: (url: string) =>
    api.post<ApiEnvelope>("/search/dismiss", { json: { url } }),
  addAllToInbox: (rows: SearchRow[]) =>
    api.post<AddAllResponse>("/search/add-all", { json: { rows } }),

  // ── Apply Queue (Phase 4) ───────────────────────────────────────────────────
  queue: () => api.get<QueueListResponse>("/queue"),
  queueResumePrompt: (id: number) =>
    api.get<QueuePromptResponse>(`/queue/${id}/resume-prompt`),
  queueResumeFromPaste: (id: number, text: string) =>
    api.post<QueueFilesResponse>(`/queue/${id}/resume-from-paste`, {
      json: { text },
    }),
  queueBatchPrompt: (ids?: number[]) =>
    api.post<QueueBatchPromptResponse>("/queue/batch-prompt", {
      json: ids && ids.length ? { ids } : {},
    }),
  queueBatchFromPaste: (text: string, ids: number[]) =>
    api.post<QueueBatchResultsResponse>("/queue/batch-from-paste", {
      json: { text, ids },
    }),
  queueGenerate: (id: number) =>
    api.post<QueueFilesResponse>(`/queue/${id}/generate`),
  queueRankPrompt: () =>
    api.post<QueueRankPromptResponse>("/queue/rank", {
      json: { mode: "prompt" },
    }),
  queueRankReply: (text: string) =>
    api.post<QueueRankReplyResponse>("/queue/rank", {
      json: { mode: "reply", text },
    }),

  // ── Resume (Phase 4) ────────────────────────────────────────────────────────
  resumePrompt: (postingText: string) =>
    api.post<QueuePromptResponse>("/resume/prompt", {
      json: { posting_text: postingText },
    }),
  resumeFromPaste: (replyText: string, postingText?: string) =>
    api.post<QueueFilesResponse>("/resume/from-paste", {
      json: postingText
        ? { reply_text: replyText, posting_text: postingText }
        : { reply_text: replyText },
    }),

  // ── Onboarding wizard + AI express lane (Phase 5) ───────────────────────────
  onboarding: () => api.get<OnboardingStateResponse>("/onboarding"),
  applyOnboarding: (answers: OnboardingAnswers) =>
    api.post<OnboardingApplyResponse>("/onboarding", { json: answers }),
  structureResume: (text: string) =>
    api.post<ResumeStructureResponse>("/onboarding/resume-structure", {
      json: { text },
    }),
  parseSalary: (text: string) =>
    api.post<SalaryParseResponse>("/onboarding/salary-parse", {
      json: { text },
    }),
  aiSetupPrompt: () => api.get<AiSetupPromptResponse>("/ai-setup/prompt"),
  applyAiSetup: (text: string) =>
    api.post<AiSetupApplyResponse>("/ai-setup/apply", { json: { text } }),

  // ── Companies: Add / validate / build / seed (Phase 5) ──────────────────────
  detectCompanies: (lines: string) =>
    api.post<CompaniesDetectResponse>("/companies/detect", {
      json: { lines },
    }),
  validateCompanies: (
    candidates: { name: string; ats: string; slug: string }[],
  ) =>
    api.post<StartRunResponse>("/companies/validate", {
      json: { candidates },
    }),
  addCompanies: (entries: CompanyAddEntry[], keepUnreachable: boolean) =>
    api.post<CompaniesAddResponse>("/companies/add", {
      json: { entries, keep_unreachable: keepUnreachable },
    }),
  buildCompanyList: (opts: BuildListOpts) =>
    api.post<StartRunResponse>("/companies/build-list", { json: { opts } }),
  seedMetro: (args: SeedMetroArgs) =>
    api.post<StartRunResponse>("/companies/seed-metro", { json: args }),
  seedPrompt: (args: { field?: string; metro?: string; limit?: number }) =>
    api.get<SeedPromptResponse>("/companies/seed-prompt", {
      params: { field: args.field, metro: args.metro, limit: args.limit },
    }),
  seedApply: (text: string, industry?: string) =>
    api.post<SeedApplyResponse>("/companies/seed-apply", {
      json: industry ? { text, industry } : { text },
    }),

  // ── Guide (Phase 5) ─────────────────────────────────────────────────────────
  guide: () => api.get<GuideResponse>("/guide"),
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

/** Optional POST /runs/daily body — run-shaping knobs (S36 parity gap P1). */
export interface DailyRunKnobs {
  /** Per-keyword pagination cap, 1–10 (CLI --max-pages; engine default 2). */
  max_pages?: number;
  /** Inbox score threshold, 0–100 (CLI --min-score; engine default). */
  min_score?: number;
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

// ── Search (Phase 4) ──────────────────────────────────────────────────────────
/** The POST /api/search body. All optional — missing fields fall back to the
 * project config server-side (keywords accepts a comma string or a list). */
export interface SearchArgs {
  keywords?: string[] | string;
  location?: string;
  min_salary?: number | null;
  save?: boolean;
  hide_tracked?: boolean;
}

/** A scored search result row (serializers.job_result) — every JobResult field
 * plus the display conveniences `salary` (formatted string) and `seen` (already
 * tracked/dismissed). The Track / Add-all routes take this row back verbatim (the
 * serializer's inverse reconstructs the JobResult), so the FULL row must round-trip
 * unchanged — hence the index signature carrying the fields the UI doesn't read. */
export interface SearchRow {
  title: string;
  company: string;
  location: string;
  url: string;
  /** Base match score (0–100); -1 = unscored (rendered blank). */
  score?: number | null;
  /** The source client's API tag (e.g. "adzuna") — shown in the Source column. */
  source_api?: string | null;
  /** Formatted salary display string (may be ""). */
  salary?: string | null;
  /** This URL is already tracked/dismissed — badge/mute it. */
  seen?: boolean;
  [key: string]: unknown;
}

/** A per-source health row from the finished search (search_job.run_search). */
export interface SearchHealthRow {
  source: string;
  count: number;
  ok: boolean;
  error: string;
  skipped_keyless: boolean;
  status: "ok" | "keyless" | "throttled" | "failed";
}

/** The search job's terminal result payload ({rows, health}). */
export interface SearchResult {
  rows: SearchRow[];
  health: SearchHealthRow[];
}

/** The generic job snapshot with the search `result` typed. `result` is null while
 * running, the {rows, health} object on done. */
export interface SearchJobSnapshot {
  ok: boolean;
  status: JobStatus;
  lines_tail: string[];
  result: SearchResult | null;
  error: string | null;
}

export interface TrackSearchResponse extends ApiEnvelope {
  added: number;
  skipped: number;
}

export interface AddAllResponse extends ApiEnvelope {
  added: number;
}

// ── Apply Queue (Phase 4) ─────────────────────────────────────────────────────
/** A queue row = an app row + the queue augmentation the /queue route adds. */
export interface QueueRow extends AppRow {
  /** URL-derived ATS label (e.g. "Greenhouse") or "". */
  ats_label: string;
  /** Referral nudge line (known contacts at the company) or "". */
  referral: string;
  /** Saved resume bundle path when docs exist for this job. */
  docs_path?: string | null;
  /** The AI fit rationale (engine column) when present — shown in the detail rail. */
  fit_rationale?: string | null;
  /** AI re-rank fit (0–100) or -1/absent; leads the queue ordering. */
  fit_score?: number | null;
  /** Base match score (0–100) or -1/absent; the queue-order tiebreak. */
  score?: number | null;
}

export interface QueueListResponse extends ApiEnvelope {
  rows: QueueRow[];
}

/** A saved DOCX file, downloadable via the gated /queue|/resume/download route. */
export interface BundleFile {
  name: string;
  download_url: string;
}

export interface QueuePromptResponse extends ApiEnvelope {
  prompt: string;
}

export interface QueueFilesResponse extends ApiEnvelope {
  files: BundleFile[];
}

export interface QueueBatchPromptResponse extends ApiEnvelope {
  prompt: string;
  ids: number[];
}

/** One entry per attempted job in a batch paste — files (saved) or error (failed). */
export type QueueBatchResultEntry =
  { id: number; files: BundleFile[] } | { id: number; error: string };

export interface QueueBatchResultsResponse extends ApiEnvelope {
  results: QueueBatchResultEntry[];
}

/** A job auto-filtered out of the fit-ranking prompt, with the reasons. */
export interface RankDropped {
  id: number | null;
  title: string | null;
  company: string | null;
  reasons: string[];
}

export interface QueueRankPromptResponse extends ApiEnvelope {
  prompt: string;
  ids: number[];
  dropped: RankDropped[];
}

export interface QueueRankReplyResponse extends ApiEnvelope {
  applied: number;
}

/** SSE endpoint (relative to /api) for a job's live event stream. Consumed via a
 * native EventSource in the Inbox run console, NOT the JSON client. */
export function jobEventsUrl(jobId: string): string {
  return `/api/jobs/${encodeURIComponent(jobId)}/events`;
}

/** Trigger a browser download of a generated resume/cover DOCX (or any gated
 * bundle file) via the locked download route. fetch → blob → object-URL → click a
 * hidden <a>, honoring the server-set filename; nothing shells to the OS (repo rule:
 * HTTP downloads only). A JSON error body (404 traversal / missing) surfaces as a
 * thrown ApiError so the caller can toast it. */
export async function downloadBundleFile(
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

// ── Onboarding wizard + AI express lane (Phase 5) ─────────────────────────────
/** The prefill dict the wizard pre-populates from (setup_wizard_core.prefill_from_existing).
 * Every field is a string except the two booleans; `salary_min` is a string (the tk
 * salary box is free-text) — parsed server-side. */
export interface OnboardingPrefill {
  roles: string;
  location: string;
  remote_ok: boolean;
  salary_min: string;
  about: string;
  industry: string;
  level: string;
}

export interface OnboardingStateResponse extends ApiEnvelope {
  onboarded: boolean;
  prefill: OnboardingPrefill;
}

/** The wizard answers POSTed on Finish. `roles` may be a list or a comma string
 * (the server accepts either); `salary_min` a free-text string or int. */
export interface OnboardingAnswers {
  roles: string[] | string;
  location: string;
  remote_ok: boolean;
  salary_min: string | number | null;
  industry: string;
  level: string;
  about: string;
  resume_text?: string;
}

export interface OnboardingApplyResponse extends ApiEnvelope {
  onboarded: boolean;
  resume_restructured: boolean;
}

export interface ResumeStructureResponse extends ApiEnvelope {
  markdown: string;
  restructured: boolean;
}

export type SalaryKind = "annual" | "hourly" | "none";

export interface SalaryParseResponse extends ApiEnvelope {
  annual: number | null;
  kind: SalaryKind;
}

export interface AiSetupPromptResponse extends ApiEnvelope {
  prompt: string;
}

/** The applied-setup summary the AI express lane echoes back (ai_setup.apply_setup). */
export interface AiSetupApplied {
  field: string;
  target_titles: string[];
  location: string;
  remote_only: boolean;
  salary_min: number | null;
  seniority: string;
  radius?: number | null;
  profile_chars: number;
}

export interface AiSetupApplyResponse extends ApiEnvelope {
  applied: AiSetupApplied;
}

// ── Companies (Phase 5) ───────────────────────────────────────────────────────
export type DetectStatus = "detected" | "direct" | "dropped";

/** One row of the Detect table (companies_detect). */
export interface CompanyCandidate {
  line: string;
  name: string;
  ats: string;
  slug: string;
  status: DetectStatus;
}

export interface CompaniesDetectResponse extends ApiEnvelope {
  candidates: CompanyCandidate[];
}

export type CompanyVerdict = "live" | "direct" | "unreachable";

/** A per-board verdict from the validate job's result. */
export interface CompanyVerdictRow {
  name: string;
  ats: string;
  slug: string;
  verdict: CompanyVerdict;
  detail: string;
  count?: number;
}

/** The validate job's terminal result payload. */
export interface CompaniesValidateResult {
  results: CompanyVerdictRow[];
}

/** The generic job snapshot with the validate `result` typed. */
export interface ValidateJobSnapshot {
  ok: boolean;
  status: JobStatus;
  lines_tail: string[];
  result: CompaniesValidateResult | null;
  error: string | null;
}

/** An entry the Add route saves (post-validate). `verdict` decides verified vs
 * unverified vs dropped; `industry` optionally tags the board. */
export interface CompanyAddEntry {
  name: string;
  ats: string;
  slug: string;
  verdict: CompanyVerdict | string;
  industry?: string;
}

export interface CompaniesAddResponse extends ApiEnvelope {
  added: number;
  verified: number;
  unverified: number;
  rejected: number;
  dropped: number;
}

/** The Build-My-List options (all optional; server allowlists + falls back to
 * the active project config). */
export interface BuildListOpts {
  metro?: string;
  industry?: string;
  national?: boolean;
  dataset?: string;
  use_inbox?: boolean;
  jobhive?: boolean;
  seed_metro?: boolean;
  seed_limit?: number | null;
  classify?: boolean;
  dry_run?: boolean;
}

export interface SeedMetroArgs {
  industry?: string;
  metro?: string;
  keyword?: string;
  limit?: number | null;
}

/** 409 body when Seed My Area has no CareerOneStop key configured. */
export interface SeedKeyConflictBody {
  ok: false;
  error: string;
  need_key: true;
}

export interface SeedPromptResponse extends ApiEnvelope {
  prompt: string;
}

/** The synchronous seed-apply result (ai_setup.apply_seed_lines). */
export interface SeedApplyResult {
  parsed: number;
  added: number;
  verified: number;
  unverified: number;
  skipped: number;
  rejected: number;
  verdicts: {
    name: string;
    ats_type: string;
    slug: string;
    verdict: string;
    detail: string;
    count?: number;
  }[];
}

export interface SeedApplyResponse extends ApiEnvelope {
  result: SeedApplyResult;
}

// ── Guide (Phase 5) ───────────────────────────────────────────────────────────
export interface GuideSection {
  heading: string;
  /** 1 = h1 (major), 2 = h2 (sub). */
  level: number;
  body: string;
}

export interface GuideResponse extends ApiEnvelope {
  sections: GuideSection[];
}

// ── Backup / restore (Phase 5) ────────────────────────────────────────────────
export interface BackupRestoreResponse extends ApiEnvelope {
  members: number;
  rollback: string | null;
}

/** Trigger a download of the data-folder backup zip (GET /api/backup/download).
 * fetch → blob → object-URL → hidden <a> click (repo rule: HTTP downloads only,
 * never shell out). A JSON error body surfaces as a thrown ApiError. */
export async function downloadBackup(): Promise<void> {
  let resp: Response;
  try {
    resp = await fetch("/api/backup/download");
  } catch (e) {
    const msg = e instanceof Error ? e.message : "network error";
    throw new ApiError(msg, 0, null);
  }
  const ctype = resp.headers.get("content-type") ?? "";
  if (!resp.ok || ctype.includes("application/json")) {
    let message = `Backup failed (${resp.status})`;
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
  a.download = "jobscout-backup.zip";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Restore the data folder from an uploaded backup zip (multipart). The JSON
 * client can't send multipart, so we build the request by hand but still unwrap
 * the {ok,...} envelope into ApiError on failure. `confirm` is required by the
 * server (destructive) — we always send true (the UI gates it behind a scary
 * ConfirmDialog first). */
export async function restoreBackup(
  file: File,
): Promise<BackupRestoreResponse> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Requested-With": "zaggregate-webui",
  };
  const fd = new FormData();
  fd.append("file", file);
  fd.append("confirm", "true");
  let resp: Response;
  try {
    resp = await fetch("/api/backup/restore", {
      method: "POST",
      headers,
      body: fd,
    });
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
      envelope.error || `Restore failed (${resp.status} ${resp.statusText})`;
    throw new ApiError(message, resp.status, body);
  }
  return body as BackupRestoreResponse;
}

/** Fetch a validate-job snapshot and read the typed {results} off `.result`
 * (same cast pattern as searchResult — the job snapshot's `error` is a nullable
 * string that doesn't fit ApiEnvelope). */
export function validateResult(jobId: string): Promise<ValidateJobSnapshot> {
  return api
    .get<ApiEnvelope & { [k: string]: unknown }>(`/jobs/${jobId}`)
    .then((r) => r as unknown as ValidateJobSnapshot);
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
