/* Cross-tab handoff for attaching the Inbox daily-run console to an already-started
 * job — the same lightweight sessionStorage pattern the Discover tab uses to hand
 * keywords to the Search tab ("zg-search-prefill"). We do NOT invent a new
 * mechanism: the writer stashes a job id, navigates to /inbox, and the Inbox reads
 * + clears it on mount, then attaches its existing <RunConsole jobId=…> to it.
 *
 * The S40 AI-first setup uses this: applying the combined AI reply starts a
 * "first_run" job on the server; the wizard writes that job id here and routes to
 * the Inbox, which picks it up and shows the live run console with zero extra
 * clicks. */

/** The sessionStorage key carrying a job id for the Inbox to attach its run
 * console to on mount. Consumed-and-cleared so a refresh doesn't resurrect it. */
export const INBOX_RUN_HANDOFF_KEY = "zg-inbox-run-job";

/** Stash a run job id for the Inbox to attach on its next mount. Best-effort
 * (sessionStorage may be unavailable); a no-op on a blank id. */
export function stashInboxRunJob(jobId: string): void {
  if (!jobId) return;
  try {
    sessionStorage.setItem(INBOX_RUN_HANDOFF_KEY, jobId);
  } catch {
    /* best-effort — the run still happens; the console just won't auto-attach */
  }
}

/** Read + CLEAR any pending Inbox run job id (call once on Inbox mount). Returns
 * null when there's nothing to attach. Clearing on read means a refresh doesn't
 * re-open a stale console. */
export function takeInboxRunJob(): string | null {
  try {
    const id = sessionStorage.getItem(INBOX_RUN_HANDOFF_KEY);
    if (id) sessionStorage.removeItem(INBOX_RUN_HANDOFF_KEY);
    return id || null;
  } catch {
    return null;
  }
}
