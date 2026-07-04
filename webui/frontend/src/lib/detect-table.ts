/* Detect-table row model for the Add Companies dialog — pure, testable.
 *
 * The Add Companies flow has three server steps (detect → validate → add). This
 * module owns the CLIENT-SIDE row state that threads through them: it takes the
 * detect candidates, overlays the validate job's per-board verdicts (matched by
 * slug), and produces the display rows + the add payload. Keeping it here means
 * the dialog is presentation-only and the merge logic is unit-tested.
 */

import type {
  CompanyCandidate,
  CompanyVerdictRow,
  CompanyAddEntry,
  DetectStatus,
  CompanyVerdict,
} from "@/api/client";

/** The per-row phase shown in the table. */
export type RowPhase =
  | "detected" // parsed, not yet validated
  | "direct" // a raw careers page (verified-manual, not probed)
  | "dropped" // the line carried no URL — reported, excluded
  | "validating" // a probe is in flight
  | "live" // probe read the board
  | "unreachable"; // dead/walled

export interface DetectRow {
  /** The raw pasted line (stable key). */
  line: string;
  name: string;
  ats: string;
  slug: string;
  phase: RowPhase;
  /** Human detail once validated (e.g. "live (12 open jobs)"). */
  detail: string;
  /** Open-jobs count on a live board, when known. */
  count?: number;
}

/** The initial rows straight from the detect endpoint — verdict not yet run. A
 * 'dropped' candidate (no URL) carries through so the user sees what was skipped
 * (inclusion over precision: report, don't silently eat). */
export function rowsFromCandidates(
  candidates: CompanyCandidate[],
): DetectRow[] {
  return candidates.map((c) => ({
    line: c.line,
    name: c.name,
    ats: c.ats,
    slug: c.slug,
    phase: detectStatusToPhase(c.status),
    detail: "",
  }));
}

function detectStatusToPhase(status: DetectStatus): RowPhase {
  switch (status) {
    case "detected":
      return "detected";
    case "direct":
      return "direct";
    case "dropped":
      return "dropped";
    default:
      return "detected";
  }
}

/** Mark every validatable row (not dropped, not a direct page) as validating —
 * used the moment the validate job starts, before verdicts stream in. */
export function markValidating(rows: DetectRow[]): DetectRow[] {
  return rows.map((r) =>
    r.phase === "dropped" || r.phase === "direct"
      ? r
      : { ...r, phase: "validating", detail: "" },
  );
}

/** Overlay the validate job's verdicts onto the rows (matched by slug). A row
 * with no matching verdict is left as-is (e.g. dropped rows, or a probe that got
 * cancelled before reaching it — those revert from 'validating' to 'detected' so
 * they don't spin forever; see reconcileUnverdicted). */
export function applyVerdicts(
  rows: DetectRow[],
  verdicts: CompanyVerdictRow[],
): DetectRow[] {
  const bySlug = new Map<string, CompanyVerdictRow>();
  for (const v of verdicts) bySlug.set(v.slug, v);
  return rows.map((r) => {
    const v = bySlug.get(r.slug);
    if (!v) return r;
    return {
      ...r,
      phase: verdictToPhase(v.verdict),
      detail: v.detail,
      count: v.count,
    };
  });
}

/** Any row still 'validating' after a job ends (cancelled mid-run) reverts to
 * 'detected' so the UI doesn't leave a permanent spinner. */
export function reconcileUnverdicted(rows: DetectRow[]): DetectRow[] {
  return rows.map((r) =>
    r.phase === "validating" ? { ...r, phase: "detected" } : r,
  );
}

function verdictToPhase(verdict: CompanyVerdict | string): RowPhase {
  switch (verdict) {
    case "live":
      return "live";
    case "direct":
      return "direct";
    case "unreachable":
      return "unreachable";
    default:
      return "unreachable";
  }
}

/** The candidates list to hand the validate endpoint — the validatable rows only
 * (a dropped row has no board to probe; a direct page is verified-manual). */
export function validatableCandidates(
  rows: DetectRow[],
): { name: string; ats: string; slug: string }[] {
  return rows
    .filter((r) => r.phase !== "dropped")
    .map((r) => ({ name: r.name, ats: r.ats, slug: r.slug }));
}

/** Build the Add payload from the current rows. Maps each row's phase to the
 * verdict the /add route gates on. Dropped rows are excluded (no board). A
 * still-'detected'/'validating' row (never validated) is sent as 'unreachable'
 * so the server's keep-unreachable gate decides — never silently saved verified.
 */
export function addEntries(
  rows: DetectRow[],
  industry?: string,
): CompanyAddEntry[] {
  const ind = (industry || "").trim();
  const out: CompanyAddEntry[] = [];
  for (const r of rows) {
    if (r.phase === "dropped" || !r.slug) continue;
    let verdict: CompanyVerdict;
    if (r.phase === "live") verdict = "live";
    else if (r.phase === "direct") verdict = "direct";
    else verdict = "unreachable"; // detected/validating/unreachable → gated
    out.push({
      name: r.name,
      ats: r.ats,
      slug: r.slug,
      verdict,
      ...(ind ? { industry: ind } : {}),
    });
  }
  return out;
}

/** Counts for the Add confirm ("N live, M unreachable — keep them?"). `willAdd`
 * excludes unreachable when keepUnreachable is false, matching the server gate,
 * so the dialog's preview is honest. */
export function addSummary(
  rows: DetectRow[],
  keepUnreachable: boolean,
): { live: number; unreachable: number; dropped: number; willAdd: number } {
  let live = 0;
  let unreachable = 0;
  let dropped = 0;
  for (const r of rows) {
    if (r.phase === "dropped" || !r.slug) {
      dropped++;
    } else if (r.phase === "live" || r.phase === "direct") {
      live++;
    } else {
      unreachable++;
    }
  }
  const willAdd = live + (keepUnreachable ? unreachable : 0);
  return { live, unreachable, dropped, willAdd };
}
