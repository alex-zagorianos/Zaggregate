/* The JobDialog form model — a faithful port of ui/job_dialog.py's field set and
 * save behavior, kept pure/testable (no React) so the dialog component stays thin.
 *
 * Field list mirrors JobDialog._save()'s result dict exactly:
 *   title, company, location, salary_text, url, status, date_applied,
 *   follow_up_date, deadline, contact, notes, offer_amount, offer_deadline,
 *   offer_notes
 * — the same keys the tk dialog writes back, so the web PATCH body is a superset
 * of nothing the engine (tracker.db.update_job) doesn't already accept. */

export type AppForm = {
  title: string;
  company: string;
  location: string;
  salary_text: string;
  url: string;
  status: string;
  date_applied: string;
  follow_up_date: string;
  deadline: string;
  contact: string;
  notes: string;
  offer_amount: string;
  offer_deadline: string;
  offer_notes: string;
};

/** Every editable field, in the order the tk dialog lays them out. Used to build
 * the form and to diff for PATCH. `contact`/`offer_*` are edit-only extras the
 * add endpoint doesn't take (create sends the CREATE_FIELDS subset). */
export const APP_FIELDS: readonly (keyof AppForm)[] = [
  "title",
  "company",
  "location",
  "salary_text",
  "url",
  "status",
  "date_applied",
  "follow_up_date",
  "deadline",
  "contact",
  "notes",
  "offer_amount",
  "offer_deadline",
  "offer_notes",
];

/** Fields POST /api/applications accepts on create (add_manual_job's kwargs).
 * The other fields (follow_up_date, deadline, contact, offer_*) are set via a
 * follow-up PATCH after create, or left for the user to add on the next edit —
 * but we keep create simple + matching the backend signature. */
export const CREATE_FIELDS: readonly (keyof AppForm)[] = [
  "title",
  "company",
  "location",
  "salary_text",
  "url",
  "status",
  "date_applied",
  "notes",
];

/** The default form for CREATE mode. Status defaults to "interested" (the tk
 * dialog's add-mode default and the backend's add_manual_job default). */
export function emptyForm(): AppForm {
  return {
    title: "",
    company: "",
    location: "",
    salary_text: "",
    url: "",
    status: "interested",
    date_applied: "",
    follow_up_date: "",
    deadline: "",
    contact: "",
    notes: "",
    offer_amount: "",
    offer_deadline: "",
    offer_notes: "",
  };
}

/** Build a form from a loaded application row (GET /api/applications/<id> .job).
 * Missing/undefined columns become "" so the inputs are always controlled. */
export function formFromJob(job: Record<string, unknown>): AppForm {
  const s = (k: keyof AppForm): string => {
    const v = job[k];
    return v === null || v === undefined ? "" : String(v);
  };
  return {
    title: s("title"),
    company: s("company"),
    location: s("location"),
    salary_text: s("salary_text"),
    url: s("url"),
    status: s("status") || "interested",
    date_applied: s("date_applied"),
    follow_up_date: s("follow_up_date"),
    deadline: s("deadline"),
    contact: s("contact"),
    notes: s("notes"),
    offer_amount: s("offer_amount"),
    offer_deadline: s("offer_deadline"),
    offer_notes: s("offer_notes"),
  };
}

/** Offer fields show only when status is offer/accepted — mirrors the tk dialog's
 * _sync_offer_visibility. */
export function showOffer(status: string): boolean {
  return status === "offer" || status === "accepted";
}

/** The PATCH body for edit mode: only the fields that CHANGED vs the loaded row,
 * so an edit is a minimal, intention-revealing update (and an unchanged save is a
 * no-op the backend returns the same row for). Trailing/leading whitespace is
 * trimmed to match the tk dialog's .strip() on every field. */
export function dirtyFields(
  original: AppForm,
  current: AppForm,
): Partial<AppForm> {
  const out: Partial<AppForm> = {};
  for (const k of APP_FIELDS) {
    const a = (original[k] ?? "").trim();
    const b = (current[k] ?? "").trim();
    if (a !== b) out[k] = b;
  }
  return out;
}

/** The CREATE body: the create-subset fields, trimmed. Empty extras are dropped
 * so we don't send a wall of "" the backend would coerce anyway. */
export function createBody(current: AppForm): Record<string, string> {
  const out: Record<string, string> = {};
  for (const k of CREATE_FIELDS) {
    const v = (current[k] ?? "").trim();
    if (v) out[k] = v;
  }
  // status always sent (defaults to interested) so create mode is explicit.
  out.status = (current.status || "interested").trim();
  return out;
}

/** Whether the form has unsaved edits vs the loaded row (drives the close guard).
 * In create mode `original` is emptyForm(), so any typed field counts as dirty. */
export function isDirty(original: AppForm, current: AppForm): boolean {
  return Object.keys(dirtyFields(original, current)).length > 0;
}
