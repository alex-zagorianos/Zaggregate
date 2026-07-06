import * as React from "react";
import {
  Loader2,
  X,
  Ban,
  Search as SearchIcon,
  ChevronDown,
} from "lucide-react";

import { endpoints, type JobStatus, type SearchResult } from "@/api/client";
import {
  appendConsoleLine,
  appendConsoleLines,
  capConsole,
} from "@/lib/sse-console";
import { useJobConsole } from "@/lib/useJobConsole";
import {
  parseLine,
  reduceProgress,
  emptyProgress,
  progressFraction,
  sourceDisplay,
  type RunProgress,
  type SourceRow,
  type SourceStatus,
} from "@/lib/search-progress";
import { JobStatusPill } from "@/components/JobStatusPill";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/* The Search run console — a bottom drawer that streams live per-source progress
 * over SSE while a search job runs, then hands the scored results back to the tab.
 *
 * The EventSource lifecycle, scroll-stick, error-reconciliation, and cancel POST
 * are the SHARED `useJobConsole` engine (webui/frontend/src/lib/useJobConsole.ts),
 * the same one driving the Inbox daily-run console. This console plugs in Search's
 * STRUCTURED progress: the `line` frames split into `@event` JSON frames (folded
 * into a determinate header + per-source row list via search-progress.parseLine +
 * reduceProgress) and plain human lines (the closing "N result(s)." summary, into
 * a collapsible raw log with the same sse-console de-dupe + cap).
 *
 * On the terminal `done` we fetch the job snapshot, read {rows, health} off
 * `.result`, and call `onResult` so the tab renders the table + health strip.
 * Cancel posts to the shared cancel route (the engine finishes in-flight sources,
 * starts no new work, scores partials — same as the tk Cancel button). */

export interface SearchRunConsoleProps {
  jobId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Fires with the scored {rows, health} when the search finishes. */
  onResult: (result: SearchResult) => void;
  /** Fires with the terminal status so the parent can clear its "running" flag. */
  onTerminal?: (status: JobStatus) => void;
}

export function SearchRunConsole({
  jobId,
  open,
  onOpenChange,
  onResult,
  onTerminal,
}: SearchRunConsoleProps) {
  const [lines, setLines] = React.useState<string[]>([]);
  const [progress, setProgress] = React.useState<RunProgress>(emptyProgress);
  const [logOpen, setLogOpen] = React.useState(false);

  // Fetch the scored result once, on the terminal done, and forward it up.
  const finish = React.useCallback(
    (id: string, terminal: JobStatus) => {
      endpoints
        .searchResult(id)
        .then((snap) => {
          if (snap.result) onResult(snap.result);
          onTerminal?.(terminal);
        })
        .catch(() => onTerminal?.(terminal));
    },
    [onResult, onTerminal],
  );

  const { status, cancelling, logRef, stickRef, onScroll, onCancel } =
    useJobConsole(jobId, {
      onReset: () => {
        setLines([]);
        setProgress(emptyProgress());
        setLogOpen(false);
      },
      onLine: (data) => {
        const parsed = parseLine(data);
        if (parsed.kind === "event") {
          setProgress((prev) => reduceProgress(prev, parsed.event));
        } else {
          // Plain human line — into the raw log (de-duped at the SSE boundary).
          setLines((prev) => capConsole(appendConsoleLine(prev, parsed.text)));
        }
      },
      onDone: (terminal) => {
        if (jobId) finish(jobId, terminal);
        else onTerminal?.(terminal);
      },
      onFailed: () => onTerminal?.("failed"),
      onReconcileLines: (tail) =>
        setLines((prev) => capConsole(appendConsoleLines(prev, tail))),
    });

  React.useEffect(() => {
    const el = logRef.current;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [lines, logOpen, logRef, stickRef]);

  if (!open) return null;

  const frac = progressFraction(progress);
  const pct = Math.round(frac * 100);

  return (
    <div
      className="fixed inset-x-0 bottom-0 z-40 mx-auto w-full max-w-[1400px] px-4 pb-4 sm:px-6"
      role="log"
      aria-live="polite"
      aria-label="Search progress"
    >
      <div className="bg-card border-border overflow-hidden rounded-lg border shadow-2xl">
        {/* Header */}
        <div className="border-border flex items-center justify-between gap-3 border-b px-4 py-2.5">
          <div className="flex items-center gap-2.5">
            <SearchIcon className="text-muted-foreground size-4" />
            <span className="text-foreground text-sm font-medium">
              Searching job boards
            </span>
            <JobStatusPill status={status} />
            {progress.total > 0 && (
              <span className="text-muted-foreground zg-num text-xs">
                {progress.completed}/{progress.total} sources
              </span>
            )}
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
              aria-label="Close search progress"
              onClick={() => onOpenChange(false)}
              className="text-muted-foreground size-8"
            >
              <X className="size-4" />
            </Button>
          </div>
        </div>

        {/* Determinate bar */}
        <div
          className="bg-secondary/60 h-1 w-full overflow-hidden"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className={cn(
              "h-full transition-[width] duration-300 ease-out",
              status === "failed" ? "bg-destructive" : "bg-primary",
            )}
            style={{ width: progress.total > 0 ? `${pct}%` : "35%" }}
          />
        </div>

        {/* Per-source rows */}
        <div className="max-h-52 overflow-y-auto px-4 py-3">
          {progress.sources.length === 0 ? (
            <p className="text-muted-foreground flex items-center gap-2 text-xs">
              <Loader2 className="size-3.5 animate-spin" />
              Building source clients…
            </p>
          ) : (
            <ul className="space-y-1">
              {progress.sources.map((s) => (
                <SourceRowLine key={s.source} row={s} />
              ))}
            </ul>
          )}
        </div>

        {/* Raw log (collapsible) — the plain summary lines land here */}
        <button
          type="button"
          onClick={() => setLogOpen((o) => !o)}
          className="text-muted-foreground hover:text-foreground border-border flex w-full items-center gap-1.5 border-t px-4 py-2 text-xs transition-colors"
        >
          <ChevronDown
            className={cn(
              "size-3.5 transition-transform",
              logOpen && "rotate-180",
            )}
          />
          {logOpen ? "Hide log" : "Show log"}
          {lines.length > 0 && (
            <span className="zg-num opacity-60">({lines.length})</span>
          )}
        </button>
        {logOpen && (
          <div
            ref={logRef}
            onScroll={onScroll}
            className="zg-num bg-[color-mix(in_oklab,var(--zg-ink)_4%,var(--zg-surface))] h-40 overflow-y-auto px-4 py-3 text-xs leading-relaxed"
          >
            {lines.length === 0 ? (
              <p className="text-muted-foreground">No log output yet.</p>
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
        )}
      </div>
    </div>
  );
}

function SourceRowLine({ row }: { row: SourceRow }) {
  const label = sourceDisplay(row.source);
  return (
    <li className="flex items-center justify-between gap-3 text-sm">
      <span className="flex min-w-0 items-center gap-2">
        <SourceDot row={row} />
        <span className="text-foreground truncate">{label}</span>
      </span>
      <span className="zg-num text-muted-foreground shrink-0 text-xs">
        {row.running ? (
          <Loader2 className="size-3.5 animate-spin" />
        ) : row.skippedKeyless ? (
          "needs key"
        ) : row.ok ? (
          `${row.count}`
        ) : (
          <span className="text-destructive">failed</span>
        )}
      </span>
    </li>
  );
}

function SourceDot({ row }: { row: SourceRow }) {
  if (row.running) {
    return (
      <span
        aria-hidden
        className="bg-primary/50 size-2 shrink-0 animate-pulse rounded-full"
      />
    );
  }
  const color = STATUS_COLOR[row.status ?? "failed"];
  return (
    <span
      aria-hidden
      className="size-2 shrink-0 rounded-full"
      style={{ backgroundColor: color }}
    />
  );
}

const STATUS_COLOR: Record<SourceStatus, string> = {
  ok: "var(--zg-success)",
  keyless: "var(--zg-warn)",
  throttled: "var(--zg-warn)",
  failed: "var(--zg-danger)",
};
