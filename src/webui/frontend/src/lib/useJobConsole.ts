import * as React from "react";

import {
  endpoints,
  jobEventsUrl,
  type JobStatus,
  type JobStatusResponse,
} from "@/api/client";
import { isAtBottom } from "@/lib/sse-console";

/* Shared run-console engine behind every SSE job drawer (Inbox daily-run,
 * Search progress, …). Extracted from the two consoles that had forked copies of
 * the EventSource lifecycle so the reconnect/error-reconciliation, scroll-stick,
 * and cancel semantics live in ONE place and can't silently drift.
 *
 * What this hook owns (identical across consoles):
 *   • the `status` (running|done|failed|cancelled) + `cancelling` state
 *   • the EventSource subscribe/teardown keyed on `jobId`
 *   • the `error`-event reconciliation: the browser fires SSE `error` for BOTH a
 *     server-sent terminal error frame AND a transport drop, so we close and
 *     fetch GET /api/jobs/<id>; on `failed` we surface it, on `done|cancelled`
 *     we run the terminal handler, otherwise (job still running) we RESUBSCRIBE
 *     ourselves — the close() we needed for the reconcile permanently disables
 *     the browser's native auto-reconnect, so a mid-run drop would otherwise
 *     detach the console forever and a finish AFTER the drop would never reach
 *     onDone (S40 live-test fix 2: the Inbox never refetched when the
 *     handoff-attached first run completed). The branching is the pure
 *     `reconcileAction` below, pinned by useJobConsole.test.ts.
 *   • the stick-to-bottom scroll ref + `onScroll` handler
 *   • the best-effort `onCancel` POST
 *
 * What each console plugs in (the genuinely per-console behavior):
 *   • `onReset()`   — clear the console's own render state for a fresh job
 *   • `onLine(data)`— fold ONE live `line` frame (raw text vs Search's `@event`)
 *   • `onDone(status)` — the terminal side effects (Inbox: invalidate queries +
 *                        toast; Search: fetch the scored result), given the
 *                        terminal status ("done" from the done frame, or
 *                        "done"/"cancelled" reconciled from a status fetch)
 *   • `onFailed(snap?)` — the failure side effect (toast), snap present when we
 *                         reconciled via a status fetch
 *   • `onReconcileLines(tail)` — how to fold the status snapshot's `lines_tail`
 *                                back into the console on reconnect
 *   • `onCancelResult(res)` / `onCancelError(err)` — cancel toasts (optional)
 */

export interface JobConsoleHandlers {
  /** Reset per-console render state when a new jobId subscribes. */
  onReset?: () => void;
  /** Fold one live `line` frame's data into the console. */
  onLine: (data: string) => void;
  /** Terminal success/cancel side effects, given the resolved terminal status.
   * `origin` distinguishes the live `done` SSE frame ("frame") from a status
   * reconciled after an `error`/drop ("reconcile") so a console can, e.g., toast
   * only on the live finish but still refresh data on a reconnected finish. */
  onDone: (status: JobStatus, origin: "frame" | "reconcile") => void;
  /** Failure side effect; `snap` present when reconciled via a status fetch. */
  onFailed?: (snap?: JobStatusResponse) => void;
  /** Fold a reconnect status snapshot's buffered tail back into the console. */
  onReconcileLines?: (tail: string[]) => void;
  /** Cancel succeeded (server ack). */
  onCancelResult?: (res: { cancelled: boolean }) => void;
  /** Cancel POST threw. */
  onCancelError?: (err: unknown) => void;
}

export interface JobConsole {
  status: JobStatus;
  cancelling: boolean;
  /** Attach to the scrollable log element. */
  logRef: React.RefObject<HTMLDivElement | null>;
  /** Whether the log is currently pinned to the tail (auto-scrolling). */
  stickRef: React.RefObject<boolean>;
  onScroll: () => void;
  onCancel: () => void;
}

/** What the error-reconcile status fetch decided (pure — pinned by
 * useJobConsole.test.ts). The SSE `error` event is ambiguous (terminal error
 * frame vs transport drop), so the hook closes the stream and fetches the job
 * status; this maps that status to the one correct next step:
 *   failed         → surface the failure (onFailed with the snapshot)
 *   done|cancelled → run the terminal handler (onDone, origin "reconcile")
 *   running/other  → the drop was MID-RUN: resubscribe. close() disabled the
 *                    browser's native retry, so the hook must reopen the stream
 *                    itself or the console detaches forever and a finish after
 *                    the drop never reaches onDone (S40 live-test fix 2). An
 *                    unknown status is treated as still-running — keep
 *                    listening rather than silently detach. */
export type ReconcileAction =
  | { kind: "failed" }
  | { kind: "terminal"; status: "done" | "cancelled" }
  | { kind: "resubscribe" };

export function reconcileAction(status: JobStatus | string): ReconcileAction {
  if (status === "failed") return { kind: "failed" };
  if (status === "done" || status === "cancelled") {
    return { kind: "terminal", status };
  }
  return { kind: "resubscribe" };
}

export function useJobConsole(
  jobId: string | null,
  handlers: JobConsoleHandlers,
): JobConsole {
  const [status, setStatus] = React.useState<JobStatus>("running");
  const [cancelling, setCancelling] = React.useState(false);

  const logRef = React.useRef<HTMLDivElement | null>(null);
  const stickRef = React.useRef(true); // follow the tail unless the user scrolls up

  // Keep the latest handlers reachable from the jobId-only effect without making
  // the subscription re-fire on every render (the callbacks are inline in the
  // consoles and change identity each render).
  const hRef = React.useRef(handlers);
  hRef.current = handlers;

  // Manual-resubscribe counter: bumping it re-runs the subscription effect for
  // the SAME job. This replaces the browser's native SSE auto-reconnect, which
  // the reconcile's es.close() permanently disables (close() sets readyState
  // CLOSED for good) — see the "resubscribe" branch below.
  const [attempt, setAttempt] = React.useState(0);

  React.useEffect(() => {
    if (!jobId) return;
    const h = hRef.current;
    setStatus("running");
    stickRef.current = true;
    h.onReset?.();

    // Armed for THIS jobId's subscription. The error-reconcile does an async
    // GET /api/jobs/<id>; the effect cleanup (jobId change or unmount) cannot
    // abort that in-flight promise, so without this guard a stale fetch that
    // resolves AFTER the user starts a new run would call hRef.current's
    // terminal handlers (now bound to the NEW job) + setStatus — flipping the
    // new run's console to done/failed and firing onDone (invalidate queries +
    // "Inbox updated" toast) on behalf of a job that is still running. `alive`
    // is flipped false in cleanup so every reconcile branch bails first (S40
    // fix: stale-job terminal handlers after jobId changes mid-flight).
    let alive = true;
    const es = new EventSource(jobEventsUrl(jobId));
    let retryTimer: number | undefined;

    es.addEventListener("line", (e) => {
      if (!alive) return;
      hRef.current.onLine((e as MessageEvent).data as string);
    });

    es.addEventListener("done", () => {
      if (!alive) return;
      setStatus("done");
      es.close();
      hRef.current.onDone("done", "frame");
    });

    es.addEventListener("error", () => {
      // Terminal error frame OR transport drop — reconcile via a status fetch.
      // close() first so the browser doesn't retry underneath the fetch; the
      // cost is that WE now own reconnection (the resubscribe branch).
      es.close();
      endpoints
        .jobStatus(jobId)
        .then((snap) => {
          // Bail if this subscription was torn down (jobId changed / unmount)
          // while the status fetch was in flight — otherwise we'd drive the
          // CURRENT render's handlers for a job that is no longer displayed.
          if (!alive) return;
          hRef.current.onReconcileLines?.(snap.lines_tail);
          const action = reconcileAction(snap.status);
          if (action.kind === "failed") {
            setStatus("failed");
            hRef.current.onFailed?.(snap);
          } else if (action.kind === "terminal") {
            setStatus(action.status);
            hRef.current.onDone(action.status, "reconcile");
          } else {
            // Still running — the drop was mid-run. The old code left this
            // branch to "the browser's reconnect", but es.close() above had
            // already disabled that, so the console silently detached forever
            // and a finish AFTER the drop never reached onDone — the S40
            // live-test bug: the handoff-attached first run completed but the
            // Inbox never refetched. Resubscribe ourselves after the same
            // backoff the stream advertises (retry: 2000); the effect re-run
            // replays the buffered tail, so no lines are lost.
            retryTimer = window.setTimeout(
              () => setAttempt((a) => a + 1),
              2000,
            );
          }
        })
        .catch(() => {
          if (!alive) return;
          setStatus("failed");
          hRef.current.onFailed?.();
        });
    });

    return () => {
      alive = false;
      es.close();
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
    };
    // Deps: jobId (a new job = a fresh subscription) + attempt (our manual
    // resubscribe after a mid-run drop). Handlers are read via hRef.current
    // (see above) so the subscription doesn't re-fire every render.
  }, [jobId, attempt]);

  const onScroll = React.useCallback(() => {
    const el = logRef.current;
    if (!el) return;
    stickRef.current = isAtBottom(
      el.scrollTop,
      el.scrollHeight,
      el.clientHeight,
    );
  }, []);

  const onCancel = React.useCallback(() => {
    if (!jobId) return;
    setCancelling(true);
    endpoints
      .cancelJob(jobId)
      .then((r) => hRef.current.onCancelResult?.(r))
      .catch((e) => hRef.current.onCancelError?.(e))
      .finally(() => setCancelling(false));
  }, [jobId]);

  return { status, cancelling, logRef, stickRef, onScroll, onCancel };
}
