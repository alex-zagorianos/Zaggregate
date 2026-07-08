/** Pure logic for the in-app auto-update flow (Settings ▸ Check for updates).
 *
 * The component owns the clicks, the timers and the toasts; everything that can be
 * decided from data lives here so it can be unit-tested without React.
 *
 * The flow, all user-clicked (PRIVACY.md: nothing calls out on a timer):
 *
 *   click "Check for updates"
 *     ├── managed:false  → offer the releases link (the v1.0.2 behaviour)
 *     ├── newer:false    → "you're up to date"
 *     ├── latest:null    → "couldn't check" (offline; NOT an error)
 *     └── newer:true     → offer "Download"
 *            click Download → poll progress until "ready" | "error"
 *              └── ready  → offer "Restart to finish"
 *                     click → the window disappears and comes back updated
 */
import type {
  UpdateApplyResponse,
  UpdateCheckResponse,
  UpdateProgressResponse,
  UpdatePhase,
} from "@/api/client";

/** How often to poll /meta/update/progress while a download is in flight. */
export const POLL_INTERVAL_MS = 500;

/** Give up polling after this long; a stuck download must not spin forever. */
export const POLL_TIMEOUT_MS = 10 * 60 * 1000;

export type CheckOutcome =
  | { kind: "unmanaged"; current: string; latest: string; url: string }
  | { kind: "unmanaged-current"; current: string }
  | { kind: "unavailable" }
  | { kind: "up-to-date"; current: string }
  | { kind: "update-ready-to-download"; latest: string }
  | { kind: "already-downloaded"; latest: string };

/** Classify an update-check response into exactly one UI outcome.
 *
 * Order matters: `pending_restart` beats `newer`, because an update already staged on
 * disk (possibly by a previous run of the app) should be applied, not re-downloaded. */
export function classifyCheck(r: UpdateCheckResponse): CheckOutcome {
  if (!r.managed) {
    if (r.latest && r.newer) {
      return {
        kind: "unmanaged",
        current: r.current,
        latest: r.latest,
        url: r.url,
      };
    }
    if (r.latest) return { kind: "unmanaged-current", current: r.current };
    return { kind: "unavailable" };
  }
  if (r.pending_restart) {
    return { kind: "already-downloaded", latest: r.latest ?? r.current };
  }
  if (r.latest && r.newer) {
    return { kind: "update-ready-to-download", latest: r.latest };
  }
  if (r.latest === null && !r.newer) {
    // A managed check that couldn't reach GitHub reports latest:null too.
    return { kind: "unavailable" };
  }
  return { kind: "up-to-date", current: r.current };
}

/** True while the download is still running and the UI should keep polling. */
export function shouldKeepPolling(phase: UpdatePhase): boolean {
  return phase === "checking" || phase === "downloading";
}

/** True when the poll loop has reached a terminal state. */
export function isTerminal(phase: UpdatePhase): boolean {
  return phase === "ready" || phase === "error";
}

/** A human label for the progress bar. Percent is only meaningful while downloading. */
export function progressLabel(p: UpdateProgressResponse): string {
  switch (p.phase) {
    case "checking":
      return "Checking…";
    case "downloading":
      return p.version
        ? `Downloading ${p.version}… ${p.percent}%`
        : `Downloading… ${p.percent}%`;
    case "ready":
      return p.version ? `Version ${p.version} is ready` : "Update is ready";
    case "error":
      return "Download failed";
    default:
      return "";
  }
}

/** Map the machine-readable `error` from POST /meta/update/apply to something a beta
 * tester can act on. An unknown code must still produce a sentence, never `undefined`. */
export function applyErrorMessage(r: UpdateApplyResponse): string {
  switch (r.error) {
    case "daily-run-active":
      return "Your scheduled daily search is running right now. Try again once it finishes — updating mid-run could corrupt it.";
    case "nothing-downloaded":
      return "Nothing has been downloaded yet. Check for updates first.";
    case "not-managed":
      return "This copy can't update itself. Download the new version from the releases page.";
    default:
      return "The update couldn't be applied. Your current version is untouched — try again, or install the new version by hand.";
  }
}

/** The toast copy for a completed check. Kept beside classifyCheck so the two can
 * never drift. Returns null when the outcome needs a richer, action-bearing toast. */
export function checkMessage(o: CheckOutcome): string | null {
  switch (o.kind) {
    case "unmanaged-current":
      return `You're running the latest version (${o.current}).`;
    case "up-to-date":
      return `You're running the latest version (${o.current}).`;
    case "unavailable":
      return "No connection, or there are no releases yet.";
    default:
      return null;
  }
}
