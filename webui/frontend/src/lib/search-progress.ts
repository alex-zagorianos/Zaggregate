/* Search run-console progress parsing — the pure core behind the Search tab's live
 * per-source progress drawer. Kept out of the component (unit-tested in
 * search-progress.test.ts, node env) because the frame protocol + the source-row
 * folding are load-bearing and subtle.
 *
 * THE FRAME CONTRACT (webui/api/search.py::EVENT_PREFIX): the search job writes to
 * its log; the SSE route emits each line as an `event: line` frame. STRUCTURED
 * progress frames are the literal prefix `@event ` followed by ONE compact JSON
 * object — the verbatim engine event dict. Any line WITHOUT that prefix is a plain
 * human status line (e.g. the closing "N result(s)." summary).
 *
 * Engine phases (search/search_job.py::run_search -> SearchEngine.run_full_search):
 *   start        { phase, total }              — total sources about to be queried
 *   source_start { phase, source }             — a source began
 *   source_done  { phase, source, count, ok,   — a source finished (health row)
 *                  error, done, total, skipped_keyless? }
 *   done         { phase, raw, deduped }        — search finished, pre-scoring counts
 *
 * `EVENT_PREFIX` here MUST equal the backend's `search.EVENT_PREFIX` — the single
 * shared sentinel. Kept literal (not imported) because the frontend has no import
 * path to Python; the search-progress.test.ts pins it. */

/** The shared sentinel (must equal webui/api/search.py::EVENT_PREFIX). */
export const EVENT_PREFIX = "@event ";

/** A single-token source health status (search_job.source_status). */
export type SourceStatus = "ok" | "keyless" | "throttled" | "failed";

/** A parsed structured progress frame — one engine phase dict. */
export type ProgressEvent =
  | { phase: "start"; total: number }
  | { phase: "source_start"; source: string }
  | {
      phase: "source_done";
      source: string;
      count: number;
      ok: boolean;
      error: string;
      done: number;
      total: number;
      skipped_keyless?: boolean;
    }
  | { phase: "done"; raw: number; deduped: number }
  | { phase: string; [k: string]: unknown };

/** A plain (non-structured) console line — rendered as text. */
export interface PlainLine {
  kind: "plain";
  text: string;
}
/** A structured progress event line. */
export interface EventLine {
  kind: "event";
  event: ProgressEvent;
}
export type ParsedLine = PlainLine | EventLine;

/** Parse ONE raw SSE console line. A line that starts with `@event ` and whose
 * remainder is valid JSON becomes an `event`; ANYTHING else (no prefix, or a
 * malformed JSON tail) is a `plain` line rendered verbatim. Never throws. */
export function parseLine(raw: string): ParsedLine {
  if (raw.startsWith(EVENT_PREFIX)) {
    const tail = raw.slice(EVENT_PREFIX.length);
    try {
      const obj = JSON.parse(tail) as unknown;
      if (obj && typeof obj === "object" && "phase" in (obj as object)) {
        return { kind: "event", event: obj as ProgressEvent };
      }
    } catch {
      // fall through to plain — a malformed frame renders as text
    }
  }
  return { kind: "plain", text: raw };
}

/** A per-source row in the live progress table. `running` = started but not done. */
export interface SourceRow {
  source: string;
  running: boolean;
  done: boolean;
  count: number;
  ok: boolean;
  error: string;
  status: SourceStatus | null; // null while still running
  skippedKeyless: boolean;
}

/** The accumulated run state the progress header renders. `total` is the source
 * count the engine announced (0 until the `start` frame); `completed` counts
 * source_done frames; `sources` is the ordered per-source list; `finished` flips
 * on the `done` frame. */
export interface RunProgress {
  total: number;
  completed: number;
  sources: SourceRow[];
  finished: boolean;
  raw: number | null;
  deduped: number | null;
}

export function emptyProgress(): RunProgress {
  return {
    total: 0,
    completed: 0,
    sources: [],
    finished: false,
    raw: null,
    deduped: null,
  };
}

/** Classify a finished source-done row into a single status token. Byte-for-byte
 * the precedence of search_job.source_status / tab_search_core.source_status so
 * the live web header agrees with the end-of-run health list:
 *   1. skipped_keyless          -> keyless
 *   2. ok && count>=0           -> ok
 *   3. 429/throttle/rate in err -> throttled
 *   4. key/auth/401/403 in err  -> keyless
 *   5. otherwise                -> failed */
export function classifySource(row: {
  ok?: boolean;
  count?: number;
  error?: string;
  skipped_keyless?: boolean;
}): SourceStatus {
  if (row.skipped_keyless) return "keyless";
  if (row.ok && (row.count ?? 0) >= 0) return "ok";
  const err = (row.error || "").toLowerCase();
  if (err.includes("429") || err.includes("throttl") || err.includes("rate"))
    return "throttled";
  if (
    err.includes("key") ||
    err.includes("auth") ||
    err.includes("401") ||
    err.includes("403")
  )
    return "keyless";
  return "failed";
}

/** Fold ONE parsed progress event into the accumulated run state, returning a NEW
 * RunProgress (never mutates `prev`, so it drops into a React setState). Plain
 * lines and unknown phases are ignored here (the console renders those separately);
 * this only tracks the structured per-source + totals state.
 *
 * A `source_start` for a source not yet seen appends a running row; a `source_done`
 * updates the matching running row (or appends if the start was missed), sets its
 * status, and bumps `completed` (idempotently — a boundary-duplicate done frame for
 * an already-done source doesn't double-count). */
export function reduceProgress(
  prev: RunProgress,
  ev: ProgressEvent,
): RunProgress {
  switch (ev.phase) {
    case "start": {
      const total = numberOr(ev.total, prev.total);
      return { ...prev, total };
    }
    case "source_start": {
      const source = String((ev as { source?: unknown }).source ?? "");
      if (!source) return prev;
      if (prev.sources.some((s) => s.source === source)) return prev;
      const rows = [
        ...prev.sources,
        {
          source,
          running: true,
          done: false,
          count: 0,
          ok: true,
          error: "",
          status: null,
          skippedKeyless: false,
        } satisfies SourceRow,
      ];
      return { ...prev, sources: rows };
    }
    case "source_done": {
      const d = ev as Extract<ProgressEvent, { phase: "source_done" }>;
      const source = String(d.source ?? "");
      if (!source) return prev;
      const status = classifySource(d);
      const filled: SourceRow = {
        source,
        running: false,
        done: true,
        count: numberOr(d.count, 0),
        ok: Boolean(d.ok),
        error: String(d.error ?? ""),
        status,
        skippedKeyless: Boolean(d.skipped_keyless),
      };
      let seen = false;
      let wasDone = false;
      const rows = prev.sources.map((s) => {
        if (s.source !== source) return s;
        seen = true;
        wasDone = s.done;
        return filled;
      });
      if (!seen) rows.push(filled);
      // Prefer the engine's own done/total when present; else derive from rows.
      const completedFromRows = rows.filter((s) => s.done).length;
      const completed =
        d.done !== undefined && !wasDone
          ? numberOr(d.done, completedFromRows)
          : completedFromRows;
      const total = numberOr(d.total, prev.total);
      return { ...prev, sources: rows, completed, total };
    }
    case "done": {
      const dn = ev as Extract<ProgressEvent, { phase: "done" }>;
      return {
        ...prev,
        finished: true,
        raw: dn.raw !== undefined ? numberOr(dn.raw, prev.raw ?? 0) : prev.raw,
        deduped:
          dn.deduped !== undefined
            ? numberOr(dn.deduped, prev.deduped ?? 0)
            : prev.deduped,
      };
    }
    default:
      return prev;
  }
}

/** The determinate-bar fraction in [0,1]. 0 when the total is unknown; clamped so a
 * stray completed>total (shouldn't happen) never overshoots. */
export function progressFraction(p: RunProgress): number {
  if (p.total <= 0) return 0;
  const f = p.completed / p.total;
  if (!Number.isFinite(f) || f < 0) return 0;
  return f > 1 ? 1 : f;
}

/** Per-status counts over the finished source rows — feeds the health summary
 * strip (ok / keyless / throttled / failed chips). Running rows are not counted. */
export interface HealthCounts {
  ok: number;
  keyless: number;
  throttled: number;
  failed: number;
}

export function healthCounts(p: RunProgress): HealthCounts {
  const c: HealthCounts = { ok: 0, keyless: 0, throttled: 0, failed: 0 };
  for (const s of p.sources) {
    if (!s.done || !s.status) continue;
    c[s.status] += 1;
  }
  return c;
}

function numberOr(v: unknown, fallback: number): number {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : fallback;
}
