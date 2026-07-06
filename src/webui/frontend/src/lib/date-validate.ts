/* Client-side date validation for the JobDialog, a faithful port of the tk
 * dialog's rule (ui/common._DATE_RE = /^\d{4}-\d{2}-\d{2}$/). The tk dialog
 * validates the date FORMAT only (not calendar validity) and lets an empty value
 * through — an empty date field just means "not set". We mirror that exactly so
 * the web dialog accepts/rejects the same strings the desktop app does.
 *
 * Interview-round `scheduled_at` may be a bare date OR an ISO datetime
 * (YYYY-MM-DDTHH:MM); the tk round dialog validates only the leading date
 * portion (sched[:10]) — isValidScheduledAt mirrors that. */

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** True when `value` is a valid YYYY-MM-DD date OR is empty (empty = unset, which
 * the tk dialog allows). Whitespace is trimmed first, matching the tk `.strip()`. */
export function isValidDate(value: string | null | undefined): boolean {
  const v = (value ?? "").trim();
  if (!v) return true;
  return DATE_RE.test(v);
}

/** True when an interview round's scheduled_at is empty, or its first 10 chars
 * are a valid date (so a bare date or an ISO datetime both pass). Mirrors the tk
 * _RoundDialog rule (`sched[:10]`). */
export function isValidScheduledAt(value: string | null | undefined): boolean {
  const v = (value ?? "").trim();
  if (!v) return true;
  return DATE_RE.test(v.slice(0, 10));
}

/** The four JobDialog date fields the tk dialog validates on save, with their
 * human labels — so the web dialog can report the same field-named error. */
export const DATE_FIELDS: readonly { key: string; label: string }[] = [
  { key: "date_applied", label: "Date Applied" },
  { key: "follow_up_date", label: "Follow-up" },
  { key: "deadline", label: "Deadline" },
  { key: "offer_deadline", label: "Offer decide-by" },
];

/** Validate all date fields on a JobDialog form value. Returns the first offending
 * field's label + value, or null when every date is valid/empty. */
export function firstBadDate(
  form: Record<string, unknown>,
): { label: string; value: string } | null {
  for (const { key, label } of DATE_FIELDS) {
    const raw = form[key];
    const value = typeof raw === "string" ? raw.trim() : "";
    if (!isValidDate(value)) return { label, value };
  }
  return null;
}
