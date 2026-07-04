import * as React from "react";
import { toast } from "sonner";
import { Loader2, X, Terminal, Ban } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/api/queries";
import type { JobStatus } from "@/api/client";
import { friendlyError, friendlyServerError } from "@/lib/friendly-error";
import {
  appendConsoleLine,
  appendConsoleLines,
  capConsole,
} from "@/lib/sse-console";
import { useJobConsole } from "@/lib/useJobConsole";
import { JobStatusPill } from "@/components/JobStatusPill";
import { Button } from "@/components/ui/button";

/* The daily-run console drawer — a bottom sheet that streams the live pipeline log
 * over SSE while "Update my Inbox now" runs.
 *
 * SSE contract (webui/api/runs.py + jobs.py): the stream opens with `retry:`, then
 * `event: line` frames (a replayed tail THEN live), and a terminal `event: done`
 * (JSON result) or `event: error` (message). The replay/live boundary can repeat a
 * line — we de-dupe adjacent identicals (sse-console.appendConsoleLine).
 *
 * The EventSource lifecycle, scroll-stick, error-reconciliation, and cancel POST
 * are the SHARED `useJobConsole` engine (webui/frontend/src/lib/useJobConsole.ts),
 * composed here with the Inbox-specific frame handling: raw-line rendering, inbox
 * query invalidation on finish, and the finish/failure toasts. On `done` we
 * invalidate the inbox queries (new rows landed) and toast a summary; on `error`
 * we toast the failure. Cancel posts to the cancel route (best-effort — the daily
 * run only honors a pre-start cancel; the server decides). */

export interface RunConsoleProps {
  jobId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called with the terminal status so the parent can clear its "running" flag. */
  onTerminal?: (status: JobStatus) => void;
}

export function RunConsole({
  jobId,
  open,
  onOpenChange,
  onTerminal,
}: RunConsoleProps) {
  const qc = useQueryClient();
  const [lines, setLines] = React.useState<string[]>([]);

  const refreshInbox = React.useCallback(() => {
    // New inbox rows may have landed — refresh the flagship + shortlist.
    qc.invalidateQueries({ queryKey: queryKeys.inboxAll });
    qc.invalidateQueries({ queryKey: queryKeys.topPicksAll });
  }, [qc]);

  const { status, cancelling, logRef, stickRef, onScroll, onCancel } =
    useJobConsole(jobId, {
      onReset: () => setLines([]),
      onLine: (data) =>
        setLines((prev) => capConsole(appendConsoleLine(prev, data))),
      onDone: (terminal, origin) => {
        refreshInbox();
        onTerminal?.(terminal);
        // Only toast the live finish; a reconnected finish refreshes silently.
        if (origin === "frame") {
          toast.success("Inbox updated", {
            description:
              "Your latest run finished. New matches are in the Inbox.",
          });
        }
      },
      onFailed: (snap) => {
        onTerminal?.("failed");
        if (snap) {
          toast.error("Run failed", {
            description: friendlyServerError(
              snap.error,
              "The pipeline stopped early.",
            ),
          });
        } else {
          toast.error("Lost the run stream", {
            description: "The connection dropped. Check the Inbox for results.",
          });
        }
      },
      onReconcileLines: (tail) =>
        setLines((prev) => capConsole(appendConsoleLines(prev, tail))),
      onCancelResult: (r) =>
        toast(r.cancelled ? "Cancel requested" : "Nothing to cancel", {
          description: r.cancelled
            ? "The run will stop at the next safe point."
            : "The run already finished or can't be interrupted.",
        }),
      onCancelError: (e) =>
        toast.error("Couldn't cancel", {
          description: friendlyError(e),
        }),
    });

  // Auto-scroll to the tail when stuck to bottom.
  React.useEffect(() => {
    const el = logRef.current;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [lines, logRef, stickRef]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-x-0 bottom-0 z-40 mx-auto w-full max-w-[1400px] px-4 pb-4 sm:px-6"
      role="log"
      aria-live="polite"
      aria-label="Daily run console"
    >
      <div className="bg-card border-border overflow-hidden rounded-lg border shadow-2xl">
        {/* Header */}
        <div className="border-border flex items-center justify-between gap-3 border-b px-4 py-2.5">
          <div className="flex items-center gap-2.5">
            <Terminal className="text-muted-foreground size-4" />
            <span className="text-foreground text-sm font-medium">
              Updating your Inbox
            </span>
            <JobStatusPill status={status} />
          </div>
          <div className="flex items-center gap-1.5">
            {status === "running" && (
              <Button
                variant="ghost"
                size="sm"
                onClick={onCancel}
                disabled={cancelling}
                className="text-muted-foreground hover:text-destructive"
              >
                <Ban className="size-3.5" />
                Cancel
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              aria-label="Close console"
              onClick={() => onOpenChange(false)}
              className="text-muted-foreground size-8"
            >
              <X className="size-4" />
            </Button>
          </div>
        </div>

        {/* Log body */}
        <div
          ref={logRef}
          onScroll={onScroll}
          className="zg-num bg-[color-mix(in_oklab,var(--zg-ink)_4%,var(--zg-surface))] h-56 overflow-y-auto px-4 py-3 text-xs leading-relaxed"
        >
          {lines.length === 0 ? (
            <p className="text-muted-foreground flex items-center gap-2">
              <Loader2 className="size-3.5 animate-spin" />
              Starting the run…
            </p>
          ) : (
            lines.map((ln, i) => (
              <div
                key={i}
                className="text-foreground/85 whitespace-pre-wrap break-words"
              >
                {ln || " "}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
