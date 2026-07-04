/* Client-side row windowing math for the Inbox table.
 *
 * The Inbox can hold ~2k rows and we render usably WITHOUT a virtualization dep
 * (plan constraint: no new deps). The strategy is incremental reveal: render the
 * first `pageSize` rows, and an IntersectionObserver sentinel bumps a `shown`
 * count by `pageSize` each time it scrolls into view. This module is the pure math
 * behind that — how many rows to render, whether more remain, and the next count —
 * so the component only wires the observer. Unit-tested in window-rows.test.ts.
 *
 * Why not TanStack Virtual: it's a real dep and a fixed-height virtualizer fights
 * the variable-height triage rows (a two-line title wraps differently than one).
 * Incremental slicing keeps the DOM bounded (a few hundred nodes at a time) while
 * every row that IS rendered is a normal, inspectable, keyboard-navigable element —
 * which matters for the roving t/d/o focus model. */

/** How many rows to reveal per step (initial page AND each "load more" bump). */
export const DEFAULT_PAGE_SIZE = 100;

/** Clamp the number of rows to render to `[0, total]`. `shown` is the running
 * reveal count the component holds in state; it can drift past `total` when the
 * list shrinks (a filter narrows, rows get dismissed), so we clamp on read. */
export function clampShown(shown: number, total: number): number {
  if (!Number.isFinite(shown) || shown < 0) return 0;
  if (shown > total) return total;
  return Math.floor(shown);
}

/** Are there more rows to reveal beyond the currently-shown count? */
export function hasMore(shown: number, total: number): boolean {
  return clampShown(shown, total) < total;
}

/** The next reveal count after a "load more" step — bump by `pageSize`, clamped to
 * `total`. Idempotent at the end (returns `total` once everything is shown). */
export function nextShown(
  shown: number,
  total: number,
  pageSize: number = DEFAULT_PAGE_SIZE,
): number {
  const step = pageSize > 0 ? pageSize : DEFAULT_PAGE_SIZE;
  return clampShown(clampShown(shown, total) + step, total);
}

/** Slice `rows` to the visible window `[0, shown)`. Pure — never mutates input.
 * The generic keeps it usable for any row type (the Inbox passes serialized inbox
 * rows). */
export function windowRows<T>(rows: readonly T[], shown: number): T[] {
  return rows.slice(0, clampShown(shown, rows.length));
}

/** A compact "showing X of Y" summary. Per inclusion-over-precision the Inbox
 * ALWAYS surfaces the unfiltered `total` (M) alongside the filtered/shown count so
 * the user knows how many jobs exist even when a view filter is hiding some. When
 * a reveal window is also hiding rows (windowed < filtered), we say "rendered".
 *
 * @param rendered  rows actually in the DOM right now (the window)
 * @param filtered  rows that survive the active view filters (server `shown`)
 * @param total     the whole unfiltered inbox (server `total`)
 */
export function shownSummary(
  rendered: number,
  filtered: number,
  total: number,
): string {
  const fmt = (n: number) => n.toLocaleString("en-US");
  // No filters narrowing: just "N of M" (or "N jobs" when all shown).
  if (filtered >= total) {
    if (rendered >= filtered)
      return `${fmt(filtered)} job${filtered === 1 ? "" : "s"}`;
    return `Showing ${fmt(rendered)} of ${fmt(filtered)}`;
  }
  // Filters are narrowing the view; always show the total M so the user knows the
  // full inbox size (inclusion-over-precision surfacing).
  if (rendered >= filtered) {
    return `${fmt(filtered)} of ${fmt(total)} shown`;
  }
  return `Showing ${fmt(rendered)} of ${fmt(filtered)} filtered · ${fmt(total)} total`;
}
