import * as React from "react";
import {
  Loader2,
  CheckCircle2,
  XCircle,
  X,
  Ban,
  Search as SearchIcon,
  ChevronDown,
} from "lucide-react";

import {
  endpoints,
  jobEventsUrl,
  type JobStatus,
  type SearchResult,
} from "@/api/client";
import {
  appendConsoleLine,
  appendConsoleLines,
  capConsole,
  isAtBottom,
} from "@/lib/sse-console";
import {
  parseLine,
  reduceProgress,
  emptyProgress,
  progressFraction,
  type RunProgress,
  type SourceRow,
  type SourceStatus,
} from "@/lib/search-progress";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/* The Search run console — a bottom drawer that streams live per-source progress
 * over SSE while a search job runs, then hands the scored results back to the tab.
 *
 * This is the Inbox RunConsole generalized for Search's STRUCTURED progress: the
 * same SSE line handling (sse-console de-dupe + cap + stick-to-bottom) drives a raw
 * log body, but a structured HEADER sits above it — a determinate bar (sources
 * done/total) plus a per-source row list with status dots, folded from the `@event`
 * JSON-line frames (search-progress.parseLine + reduceProgress). Plain lines (the
 * closing "N result(s)." summary) render in the raw log.
 *
 * On the terminal `done` frame we fetch the job snapshot, read {rows, health} off
 * `.result`, and call `onResult` so the tab renders the table + health strip. Cancel
 * posts to the shared cancel route (the engine finishes in-flight sources, starts no
 * new work, scores partials — same as the tk Cancel button). */

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
  const [status, setStatus] = React.useState<JobStatus>("running");
  const [cancelling, setCancelling] = React.useState(false);
  const [logOpen, setLogOpen] = React.useState(false);

  const logRef = React.useRef<HTMLDivElement | null>(null);
  const stickRef = React.useRef(true);

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

  React.useEffect(() => {
    if (!jobId) return;
    setLines([]);
    setProgress(emptyProgress());
    setStatus("running");
    setLogOpen(false);
    stickRef.current = true;

    const es = new EventSource(jobEventsUrl(jobId));

    es.addEventListener("line", (e) => {
      const data = (e as MessageEvent).data as string;
      const parsed = parseLine(data);
      if (parsed.kind === "event") {
        setProgress((prev) => reduceProgress(prev, parsed.event));
      } else {
        // Plain human line — into the raw log (de-duped at the SSE boundary).
        setLines((prev) => capConsole(appendConsoleLine(prev, parsed.text)));
      }
    });

    es.addEventListener("done", () => {
      setStatus("done");
      es.close();
      finish(jobId, "done");
    });

    es.addEventListener("error", () => {
      // Transport drop OR a server error frame — reconcile via a status fetch.
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
          } else if (snap.status === "done" || snap.status === "cancelled") {
            setStatus(snap.status);
            finish(jobId, snap.status);
          }
        })
        .catch(() => {
          setStatus("failed");
          onTerminal?.("failed");
        });
    });

    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  React.useEffect(() => {
    const el = logRef.current;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [lines, logOpen]);

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
      .catch(() => {
        /* best-effort — the console surfaces the terminal state either way */
      })
      .finally(() => setCancelling(false));
  };

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
            <StatusPill status={status} />
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

/** Strip the "Client" suffix and title-case the source class name for display
 * (AdzunaClient -> Adzuna, CareerOneStopClient -> CareerOneStop). */
function sourceDisplay(source: string): string {
  return source.replace(/Client$/i, "") || source;
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
