/* Outreach note selection (B5). Mirrors the server's `outreach.followup_stage`:
 * an interview has "happened" — so a THANK-YOU is owed rather than a cold
 * follow-up — once the application has at least one interview round OR its status
 * is at/past an interview stage. The server is the source of truth for the note
 * that gets drafted (it returns `stage`); this is a client-side hint used only to
 * label the "Draft follow-up" / "Draft thank-you" button before the call. */

/** Statuses that imply an interview has already taken place. Kept in sync with
 * `outreach._INTERVIEW_STATUSES` (tracker.db.STATUSES). */
export const INTERVIEW_STATUSES = new Set([
  "phone_screen",
  "interview",
  "offer",
  "accepted",
]);

/** True when an interview has happened: a round is logged, or the status is
 * at/past an interview stage. Drives the follow-up-vs-thank-you button label. */
export function hasInterviewHappened(
  status: string,
  roundCount: number,
): boolean {
  if (roundCount > 0) return true;
  return INTERVIEW_STATUSES.has((status || "").trim().toLowerCase());
}
