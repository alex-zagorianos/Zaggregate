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
 *     we run the terminal handler, otherwise we leave the browser to reconnect.
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

  React.useEffect(() => {
    if (!jobId) return;
    const h = hRef.current;
    setStatus("running");
    stickRef.current = true;
    h.onReset?.();

    const es = new EventSource(jobEventsUrl(jobId));

    es.addEventListener("line", (e) => {
      hRef.current.onLine((e as MessageEvent).data as string);
    });

    es.addEventListener("done", () => {
      setStatus("done");
      es.close();
      hRef.current.onDone("done", "frame");
    });

    es.addEventListener("error", () => {
      // Terminal error frame OR transport drop — reconcile via a status fetch.
      es.close();
      endpoints
        .jobStatus(jobId)
        .then((snap) => {
          hRef.current.onReconcileLines?.(snap.lines_tail);
          if (snap.status === "failed") {
            setStatus("failed");
            hRef.current.onFailed?.(snap);
          } else if (snap.status === "done" || snap.status === "cancelled") {
            setStatus(snap.status);
            hRef.current.onDone(snap.status, "reconcile");
          }
          // else: a reconnect the browser handles — leave the stream alone.
        })
        .catch(() => {
          setStatus("failed");
          hRef.current.onFailed?.();
        });
    });

    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

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
