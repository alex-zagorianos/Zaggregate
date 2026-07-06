/* Apply Queue ordering — the pure comparator behind the ranked queue list.
 *
 * PARITY (webui/api/queue.py::_ranked_interested + ui/tab_queue.py
 * ApplyQueueTab.refresh): the queue is every 'interested' application sorted by
 * `fit_score` desc THEN `score` desc, with a MISSING/unscored value treated as -1
 * (so a fit-scored row always outranks an unscored one, and among unscored rows the
 * base score breaks the tie). The Python sort is:
 *
 *     jobs.sort(key=lambda j: (j.get("fit_score") or -1, j.get("score") or -1),
 *               reverse=True)
 *
 * The server already returns rows in this order, so the frontend does NOT re-sort in
 * production — but the comparator is unit-tested here to PROVE the web ordering
 * matches the tk twin, and is available if a client-side re-sort is ever needed
 * (e.g. after an optimistic mutation). Pure + tested. */

/** The minimal shape the comparator reads (a superset of the real AppRow). */
export interface QueueSortable {
  fit_score?: number | null;
  score?: number | null;
  [k: string]: unknown;
}

/** The Python `x or -1` rule: null / undefined / 0 / NaN / non-numeric all collapse
 * to -1 (Python's `0 or -1` is -1, matching an unscored row). A real numeric value
 * (including negatives other than via falsy 0) passes through. */
export function rankValue(v: number | null | undefined): number {
  if (v === null || v === undefined) return -1;
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return -1;
  // Python treats 0 as falsy -> -1; mirror that so a 0 fit sorts like unscored.
  if (n === 0) return -1;
  return n;
}

/** Compare two queue rows for a DESCENDING sort (fit-else-score). Returns <0 when
 * `a` should come first. Ties (equal fit AND equal score) return 0 — a stable sort
 * then preserves input order, matching Python's stable `list.sort`. */
export function compareQueue(a: QueueSortable, b: QueueSortable): number {
  const af = rankValue(a.fit_score);
  const bf = rankValue(b.fit_score);
  if (af !== bf) return bf - af; // higher fit first
  const as = rankValue(a.score);
  const bs = rankValue(b.score);
  return bs - as; // then higher score first
}

/** Sort a copy of `rows` into queue order (fit-else-score desc). Does NOT mutate the
 * input. Uses a stable sort (Array.prototype.sort is stable in modern engines) so
 * equal-rank rows keep their server order. */
export function sortQueue<T extends QueueSortable>(rows: readonly T[]): T[] {
  return [...rows].sort(compareQueue);
}

/** The 1-based display rank for each row in queue order — the "#" column. Rows are
 * assumed already in order (the server's order); this is a straight enumeration,
 * NOT a re-sort, so it never disagrees with the rendered order. */
export function withRank<T>(rows: readonly T[]): (T & { rank: number })[] {
  return rows.map((r, i) => ({ ...r, rank: i + 1 }));
}
