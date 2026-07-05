/* "New since your last visit" (B7 item 4) — a frontend-only, per-project stamp of
 * the last time the user looked at the Inbox, and the count of rows that arrived
 * after it. Pure logic here (localStorage read/write + the comparison); the Inbox
 * tab wires it to a dismissable banner chip.
 *
 * The stamp is keyed per project so switching campaigns doesn't cross-count. We
 * store the millisecond epoch of the last visit; on load we count rows whose
 * newest timestamp (created, falling back to date_added) is strictly newer than
 * the stored stamp. First-ever visit (no stamp) counts nothing — there's no
 * "before" to compare against, and we don't want to greet a brand-new project by
 * calling its whole starter inbox "new". */

const KEY_PREFIX = "zg:inbox-last-visit:";

/** The localStorage key for a project's last-visit stamp. A blank/unknown slug
 * falls back to a shared "default" bucket so the feature still works before the
 * active project resolves. */
export function lastVisitKey(project: string | null | undefined): string {
  const slug = (project || "").trim() || "default";
  return `${KEY_PREFIX}${slug}`;
}

/** A row's newest timestamp as an epoch-ms number, or null when neither `created`
 * nor `date_added` parses. Mirrors the Inbox Posted column's created→date_added
 * fallback so "new" tracks the same date the user sees. */
export function rowTimestamp(row: {
  created?: string | null;
  date_added?: string | null;
}): number | null {
  for (const raw of [row.created, row.date_added]) {
    const s = String(raw || "").trim();
    if (!s) continue;
    const t = Date.parse(s);
    if (!Number.isNaN(t)) return t;
  }
  return null;
}

/** Read the stored last-visit stamp (epoch ms) for a project, or null when there
 * is none / it's unparseable / storage is unavailable. Never throws. */
export function readLastVisit(
  project: string | null | undefined,
  storage: Pick<Storage, "getItem"> | undefined = safeStorage(),
): number | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(lastVisitKey(project));
    if (!raw) return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

/** Write the last-visit stamp for a project (defaults to now). Best-effort — a
 * private-mode / quota rejection is swallowed. Returns the stamp written. */
export function writeLastVisit(
  project: string | null | undefined,
  when: number = Date.now(),
  storage: Pick<Storage, "setItem"> | undefined = safeStorage(),
): number {
  try {
    storage?.setItem(lastVisitKey(project), String(when));
  } catch {
    // ignore — the feature degrades to "no banner", never an error
  }
  return when;
}

/** Count rows whose newest timestamp is strictly after `since`. `since=null`
 * (no prior visit) counts nothing — there's no baseline to compare against. */
export function countNewSince(
  rows: { created?: string | null; date_added?: string | null }[],
  since: number | null,
): number {
  if (since === null) return 0;
  let n = 0;
  for (const r of rows) {
    const t = rowTimestamp(r);
    if (t !== null && t > since) n += 1;
  }
  return n;
}

/** localStorage if it's usable, else undefined (SSR / disabled storage). Guards
 * every access so the feature is inert rather than throwing where storage is off. */
function safeStorage(): Storage | undefined {
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      return window.localStorage;
    }
  } catch {
    // access itself can throw in locked-down contexts
  }
  return undefined;
}
