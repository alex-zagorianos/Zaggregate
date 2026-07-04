/* Relative-time formatters shared by the Inbox table (posted date) and the Inbox
 * badge strip (last-run timestamp). Two distinct formats — kept as two named
 * exports rather than unified, since callers want different granularity — but
 * ported here verbatim (same thresholds/output) from their former per-file
 * copies so both keep behaving exactly as before. */

/** A compact posted label from a job's `created`/`date_added` date, shown as a
 * relative age. Blank → "—". Used by the Inbox table's Posted column. */
export function postedLabel(raw: string | null | undefined): string {
  const s = String(raw || "").trim();
  if (!s) return "—";
  const t = Date.parse(s);
  if (Number.isNaN(t)) return s;
  const days = Math.floor((Date.now() - t) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "1d";
  if (days < 30) return `${days}d`;
  const months = Math.floor(days / 30);
  return `${months}mo`;
}

/** A compact relative time ("2h ago", "just now") from an ISO-ish timestamp;
 * falls back to the raw string when it can't be parsed (never blank). Used by
 * the Inbox badge strip's "Last run" pill. */
export function relTime(ts: string | null | undefined): string {
  if (!ts) return "—";
  const t = Date.parse(ts);
  if (Number.isNaN(t)) return ts;
  const secs = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (secs < 45) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  const wks = Math.floor(days / 7);
  return `${wks}w ago`;
}
