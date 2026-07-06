/* Batch resume-paste result mapping — the pure core behind the Apply Queue "Paste
 * batch replies" flow.
 *
 * The batch round-trip is: /queue/batch-prompt returns an ordered `ids` list (the
 * batch order; reply slot N maps to ids[N-1]); the user pastes the AI's multi-job
 * reply; /queue/batch-from-paste returns `results:[{id, files}|{id, error}]` — one
 * entry per matched/attempted job (webui/api/queue.py::batch_from_paste). This
 * module folds that server response back against the QUEUE ROWS so the UI can render
 * a per-row outcome list (saved with download buttons / failed with the error /
 * still-pending because the reply omitted that slot), matching the tk tab's
 * "saved X/N, M missing from the reply" summary.
 *
 * Pure + unit-tested; no React, no network. */

export interface BatchFile {
  name: string;
  download_url: string;
}

/** One raw result entry from /queue/batch-from-paste. */
export type BatchResultEntry =
  { id: number; files: BatchFile[] } | { id: number; error: string };

/** The per-row outcome the UI renders. `saved` carries the download files; `failed`
 * carries the DOCX/save error; `missing` means the job was in the batch but the
 * reply had no slot for it (never in the results list). */
export type BatchOutcome =
  | {
      id: number;
      title: string;
      company: string;
      kind: "saved";
      files: BatchFile[];
    }
  | {
      id: number;
      title: string;
      company: string;
      kind: "failed";
      error: string;
    }
  | { id: number; title: string; company: string; kind: "missing" };

/** The minimal row shape needed to label an outcome (title/company). */
export interface BatchRow {
  id: number;
  title?: string | null;
  company?: string | null;
}

/** Is a raw entry a failure (has an `error`) vs a save (has `files`)? */
export function isBatchError(
  e: BatchResultEntry,
): e is { id: number; error: string } {
  return "error" in e && typeof (e as { error?: unknown }).error === "string";
}

/** Fold the server `results` against the batch `ids` (the order returned by
 * batch-prompt) and the queue `rows` (for labels) into an ordered outcome list —
 * ONE entry per batched id, in batch order. An id present in `results` with `files`
 * -> saved; with `error` -> failed; ABSENT from `results` -> missing (the reply
 * skipped that slot). Rows not found in `rows` still get an entry (blank labels) so
 * the count stays honest.
 *
 * @param ids     the batch order (ids[N-1] is reply slot N)
 * @param results the raw server results (any subset/order of ids)
 * @param rows    the current queue rows, for title/company labels */
export function mapBatchResults(
  ids: readonly number[],
  results: readonly BatchResultEntry[],
  rows: readonly BatchRow[],
): BatchOutcome[] {
  const byId = new Map<number, BatchRow>();
  for (const r of rows) byId.set(r.id, r);
  const resultById = new Map<number, BatchResultEntry>();
  for (const e of results) resultById.set(e.id, e);

  return ids.map((id) => {
    const row = byId.get(id);
    const title = String(row?.title ?? "");
    const company = String(row?.company ?? "");
    const entry = resultById.get(id);
    if (!entry) return { id, title, company, kind: "missing" as const };
    if (isBatchError(entry))
      return {
        id,
        title,
        company,
        kind: "failed" as const,
        error: entry.error,
      };
    return { id, title, company, kind: "saved" as const, files: entry.files };
  });
}

export interface BatchSummary {
  saved: number;
  failed: number;
  missing: number;
  total: number;
}

/** Roll an outcome list into counts for the "saved X/N" summary line. */
export function summarizeBatch(
  outcomes: readonly BatchOutcome[],
): BatchSummary {
  let saved = 0;
  let failed = 0;
  let missing = 0;
  for (const o of outcomes) {
    if (o.kind === "saved") saved += 1;
    else if (o.kind === "failed") failed += 1;
    else missing += 1;
  }
  return { saved, failed, missing, total: outcomes.length };
}

/** A short human summary of a batch outcome list, matching the tk status line
 * ("Batch: saved docs for X/N job(s). M missing from the reply — re-paste or run
 * singly."). Empty string for an empty batch. */
export function batchSummaryLine(outcomes: readonly BatchOutcome[]): string {
  const s = summarizeBatch(outcomes);
  if (s.total === 0) return "";
  let text = `Saved docs for ${s.saved}/${s.total} job${s.total === 1 ? "" : "s"}.`;
  if (s.failed > 0) text += ` ${s.failed} failed${s.failed === 1 ? "" : ""}.`;
  if (s.missing > 0)
    text += ` ${s.missing} missing from the reply — re-paste or run singly.`;
  return text;
}
