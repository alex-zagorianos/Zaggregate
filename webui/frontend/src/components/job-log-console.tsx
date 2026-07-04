import * as React from "react";
import { Loader2, Ban } from "lucide-react";

import {
  endpoints,
  type JobStatus,
  type JobStatusResponse,
} from "@/api/client";
import {
  appendConsoleLine,
  appendConsoleLines,
  capConsole,
} from "@/lib/sse-console";
import { useJobConsole } from "@/lib/useJobConsole";
import { JobStatusPill } from "@/components/JobStatusPill";
import { Button } from "@/components/ui/button";

/* A plain streaming-log console for engine jobs that emit human text lines (no
 * structured @event frames): Add-Companies validate, Build-My-List, Seed-My-Area.
 * It's the log-only twin of SearchRunConsole — same shared `useJobConsole` engine
 * (EventSource lifecycle, error-reconciliation, scroll-stick, cancel), just a
 * scrolling <pre> instead of a per-source progress list.
 *
 * On the terminal `done` it fetches the job snapshot and hands `result` (the
 * engine's summary dict — validate verdicts, build/seed summary) back to the
 * caller via onResult, plus the terminal status via onTerminal. Rendered inline
 * inside a dialog (not a fixed drawer), so it's `title`-labelled and sizes to its
 * container. */

export interface JobLogConsoleProps {
  jobId: string | null;
  title: string;
  /** Terminal result payload (the job snapshot's `.result`), null on failure. */
  onResult?: (result: unknown, status: JobStatus) => void;
  /** Terminal status (done|failed|cancelled) — always fires. */
  onTerminal?: (status: JobStatus) => void;
  /** Hide the Cancel button (e.g. a short validate the user shouldn't interrupt). */
  cancellable?: boolean;
}

export function JobLogConsole({
  jobId,
  title,
  onResult,
  onTerminal,
  cancellable = true,
}: JobLogConsoleProps) {
  const [lines, setLines] = React.useState<string[]>([]);

  const finish = React.useCallback(
    (id: string, terminal: JobStatus) => {
      endpoints
        .jobStatus(id)
        .then((snap: JobStatusResponse) => {
          onResult?.(snap.result, terminal);
          onTerminal?.(terminal);
        })
        .catch(() => {
          onResult?.(null, terminal);
          onTerminal?.(terminal);
        });
    },
    [onResult, onTerminal],
  );

  const { status, cancelling, logRef, stickRef, onScroll, onCancel } =
    useJobConsole(jobId, {
      onReset: () => setLines([]),
      onLine: (data) =>
        setLines((prev) => capConsole(appendConsoleLine(prev, data))),
      onDone: (terminal) => {
        if (jobId) finish(jobId, terminal);
        else onTerminal?.(terminal);
      },
      onFailed: (snap) => {
        onResult?.(null, "failed");
        onTerminal?.("failed");
        if (snap?.lines_tail?.length)
          setLines((prev) =>
            capConsole(appendConsoleLines(prev, snap.lines_tail)),
          );
      },
      onReconcileLines: (tail) =>
        setLines((prev) => capConsole(appendConsoleLines(prev, tail))),
    });

  React.useEffect(() => {
    const el = logRef.current;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [lines, logRef, stickRef]);

  return (
    <div className="border-border bg-card overflow-hidden rounded-md border">
      <div className="border-border flex items-center justify-between gap-3 border-b px-3 py-2">
        <div className="flex items-center gap-2.5">
          <span className="text-foreground text-sm font-medium">{title}</span>
          <JobStatusPill status={status} />
        </div>
        {cancellable && status === "running" && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onCancel}
            disabled={cancelling}
            className="text-muted-foreground hover:text-destructive h-7"
          >
            {cancelling ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Ban className="size-3.5" />
            )}
            Cancel
          </Button>
        )}
      </div>
      <div
        ref={logRef}
        onScroll={onScroll}
        className="zg-num bg-[color-mix(in_oklab,var(--zg-ink)_4%,var(--zg-surface))] h-56 overflow-y-auto px-3 py-2.5 text-xs leading-relaxed"
        role="log"
        aria-live="polite"
        aria-label={title}
      >
        {lines.length === 0 ? (
          <p className="text-muted-foreground flex items-center gap-2">
            <Loader2 className="size-3.5 animate-spin" />
            Starting…
          </p>
        ) : (
          lines.map((ln, i) => (
            <div
              key={i}
              className="text-foreground/85 break-words whitespace-pre-wrap"
            >
              {ln || " "}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
