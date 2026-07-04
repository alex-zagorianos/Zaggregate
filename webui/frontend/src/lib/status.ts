/* Application-status vocabulary for the Tracker + Board + JobDialog.
 *
 * The canonical list of statuses and their human labels is SERVED by the backend
 * (GET /api/applications/<id> returns `statuses` + `status_labels`, and
 * GET /api/board labels each column) — this module NEVER hard-codes the set so a
 * future engine status flows through without a frontend change. What lives here
 * is purely presentational + pure/testable:
 *   - statusVar(status): the --zg-status-* CSS variable for a status
 *   - statusLabel(status, labels?): label lookup with a Title-Case fallback
 *   - TERMINAL_STATUSES: the outcome stages the board renders calmer (mirrors
 *     ui/kanban_core._TERMINAL) — used ONLY for muted styling, never to gate a
 *     move (the server's forward_targets is the source of truth for moves). */

/** The status → --zg-status-* token. The token names are `--zg-status-<status>`
 * with underscores turned into hyphens (phone_screen → phone-screen), matching
 * scripts/gen_web_tokens.py. An unknown status falls back to a neutral token so
 * the chip never renders an invalid var(). */
export function statusVar(status: string | null | undefined): string {
  const s = (status ?? "").trim();
  if (!s) return "var(--zg-status-withdrawn)";
  const slug = s.replace(/_/g, "-");
  return `var(--zg-status-${slug})`;
}

/** Human label for a status. Prefer the server-provided `labels` map; fall back
 * to a Title-Cased version of the raw key (interested → Interested,
 * phone_screen → Phone Screen) so a never-before-seen status still reads well. */
export function statusLabel(
  status: string | null | undefined,
  labels?: Record<string, string> | null,
): string {
  const s = (status ?? "").trim();
  if (!s) return "—";
  const fromMap = labels?.[s];
  if (fromMap) return fromMap;
  return s
    .split("_")
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}

/** Outcome/terminal stages — rendered visually calmer (muted headers) on the
 * board. Mirrors ui/kanban_core._TERMINAL. Presentational only. */
export const TERMINAL_STATUSES: ReadonlySet<string> = new Set([
  "accepted",
  "rejected",
  "withdrawn",
  "ghosted",
]);

export function isTerminal(status: string | null | undefined): boolean {
  return TERMINAL_STATUSES.has((status ?? "").trim());
}
