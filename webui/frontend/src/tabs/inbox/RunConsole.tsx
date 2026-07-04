import * as React from "react";
import { toast } from "sonner";
import { Loader2, CheckCircle2, XCircle, X, Terminal, Ban } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/api/queries";
import {
  endpoints,
  jobEventsUrl,
  ApiError,
  type JobStatus,
} from "@/api/client";
import {
  appendConsoleLine,
  appendConsoleLines,
  capConsole,
  isAtBottom,
} from "@/lib/sse-console";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/* The daily-run console drawer — a bottom sheet that streams the live pipeline log
 * over SSE while "Update my Inbox now" runs.
 *
 * SSE contract (webui/api/runs.py + jobs.py): the stream opens with `retry:`, then
 * `event: line` frames (a replayed tail THEN live), and a terminal `event: done`
 * (JSON result) or `event: error` (message). The replay/live boundary can repeat a
 * line — we de-dupe adjacent identicals (sse-console.appendConsoleLine).
 *
 * Auto-scroll sticks to the bottom UNLESS the user scrolls up to read history.
 * On `done` we invalidate the inbox queries (new rows landed) and toast a summary;
 * on `error` we toast the failure. Cancel posts to the cancel route (best-effort —
 * the daily run only honors a pre-start cancel; the button is always shown but the
 * server decides). */

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
  const [status, setStatus] = React.useState<JobStatus>("running");
  const [cancelling, setCancelling] = React.useState(false);

  const logRef = React.useRef<HTMLDivElement | null>(null);
  const stickRef = React.useRef(true); // follow the tail unless the user scrolls up

  // (Re)subscribe whenever the job id changes. Reset the buffer for a fresh job.
  React.useEffect(() => {
    if (!jobId) return;
    setLines([]);
    setStatus("running");
    stickRef.current = true;

    const es = new EventSource(jobEventsUrl(jobId));

    es.addEventListener("line", (e) => {
      const data = (e as MessageEvent).data as string;
      setLines((prev) => capConsole(appendConsoleLine(prev, data)));
    });

    es.addEventListener("done", () => {
      setStatus("done");
      es.close();
      // New inbox rows may have landed — refresh the flagship + shortlist.
      qc.invalidateQueries({ queryKey: queryKeys.inboxAll });
      qc.invalidateQueries({ queryKey: queryKeys.topPicksAll });
      onTerminal?.("done");
      toast.success("Inbox updated", {
        description: "Your latest run finished. New matches are in the Inbox.",
      });
    });

    es.addEventListener("error", (e) => {
      // The SSE `error` event fires both for a server-sent terminal error frame
      // AND for a transport drop. Reconcile via a status fetch: if the job failed,
      // surface it; if it actually finished, treat as done; otherwise it's a
      // reconnect the browser handles — leave the stream alone.
      const raw = (e as MessageEvent).data as string | undefined;
      es.close();
      endpoints
        .jobStatus(jobId)
        .then((snap) => {
          setLines((prev) =>
            capConsole(appendConsoleLines(prev, snap.lines_tail)),
          );
          if (snap.status === "failed") {
            setStatus("failed");
            onTerminal?.("failed");
            toast.error("Run failed", {
              description: snap.error || raw || "The pipeline stopped early.",
            });
          } else if (snap.status === "done" || snap.status === "cancelled") {
            setStatus(snap.status);
            qc.invalidateQueries({ queryKey: queryKeys.inboxAll });
            qc.invalidateQueries({ queryKey: queryKeys.topPicksAll });
            onTerminal?.(snap.status);
          }
        })
        .catch(() => {
          setStatus("failed");
          onTerminal?.("failed");
          toast.error("Lost the run stream", {
            description: "The connection dropped. Check the Inbox for results.",
          });
        });
    });

    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  // Auto-scroll to the tail when stuck to bottom.
  React.useEffect(() => {
    const el = logRef.current;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [lines]);

  const onScroll = () => {
    const el = logRef.current;
    if (!el) return;
    stickRef.current = isAtBottom(
      el.scrollTop,
      el.scrollHeight,
      el.clientHeight,
    );
  };

  const onCancel = () => {
    if (!jobId) return;
    setCancelling(true);
    endpoints
      .cancelJob(jobId)
      .then((r) => {
        if (r.cancelled) {
          toast("Cancel requested", {
            description: "The run will stop at the next safe point.",
          });
        } else {
          toast("Nothing to cancel", {
            description: "The run already finished or can't be interrupted.",
          });
        }
      })
      .catch((e) =>
        toast.error("Couldn't cancel", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
      )
      .finally(() => setCancelling(false));
  };

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
            <StatusPill status={status} />
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
                {ln || " "}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: JobStatus }) {
  const map: Record<
    JobStatus,
    { label: string; icon: React.ReactNode; cls: string }
  > = {
    running: {
      label: "Running",
      icon: <Loader2 className="size-3 animate-spin" />,
      cls: "text-primary border-primary/40 bg-primary/10",
    },
    done: {
      label: "Done",
      icon: <CheckCircle2 className="size-3" />,
      cls: "text-[var(--zg-success)] border-[var(--zg-success)]/40 bg-[var(--zg-success)]/12",
    },
    cancelled: {
      label: "Cancelled",
      icon: <Ban className="size-3" />,
      cls: "text-muted-foreground border-border bg-secondary",
    },
    failed: {
      label: "Failed",
      icon: <XCircle className="size-3" />,
      cls: "text-destructive border-destructive/40 bg-destructive/10",
    },
  };
  const s = map[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-[var(--radius-chip)] border px-1.5 py-0.5 text-[0.7rem] font-medium",
        s.cls,
      )}
    >
      {s.icon}
      {s.label}
    </span>
  );
}
