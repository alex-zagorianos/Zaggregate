import * as React from "react";
import { toast } from "sonner";
import {
  Inbox,
  RefreshCw,
  CheckCircle2,
  XCircle,
  ExternalLink,
  Loader2,
  PanelRightClose,
  PanelRightOpen,
} from "lucide-react";

import {
  useInbox,
  useTrackInboxRow,
  useDismissBulk,
  useUndoDismiss,
} from "@/api/queries";
import {
  endpoints,
  ApiError,
  type InboxRow,
  type RunConflictBody,
} from "@/api/client";
import {
  makeDefaultFilters,
  toParams,
  type InboxFilterState,
} from "@/lib/inbox-filter-state";
import {
  DEFAULT_PAGE_SIZE,
  hasMore,
  nextShown,
  windowRows,
  shownSummary,
} from "@/lib/window-rows";
import { useRegisterCommands, type AppCommand } from "@/lib/app-commands";
import { ScoreChip } from "@/components/score-chip";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import { InboxFilterBar } from "./InboxFilterBar";
import { InboxBadges } from "./InboxBadges";
import { InboxDetail } from "./InboxDetail";
import { AiMenu } from "./AiMenu";
import { RunConsole } from "./RunConsole";

/* Inbox — THE flagship triage screen.
 *
 * Layout: a full-height split — the filtered jobs table on the left, a collapsible
 * detail pane on the right (the selected row's fit rationale / score / preview).
 * The run console is an overlay drawer at the bottom while a daily run streams.
 *
 * Triage is keyboard-first: a roving-focus table with ArrowUp/Down navigation and
 * t (track) / d (dismiss) / o (open) on the focused row, plus Shift-click range
 * select and a "Dismiss all shown" bulk action. Both single and bulk dismiss show
 * an Undo toast wired to the undo-dismiss endpoint.
 *
 * INCLUSION OVER PRECISION: the filter bar only ever changes what's SHOWN; the
 * "N of M" line always surfaces the full inbox total, and dismiss is the sole drop
 * mechanism (there is no delete). */

export function InboxTab() {
  const [filters, setFilters] =
    React.useState<InboxFilterState>(makeDefaultFilters);
  const params = React.useMemo(() => toParams(filters), [filters]);
  const query = useInbox(params);

  const track = useTrackInboxRow();
  const dismissBulk = useDismissBulk();
  const undoDismiss = useUndoDismiss();

  const rows = React.useMemo(() => query.data?.rows ?? [], [query.data]);
  const total = query.data?.total ?? 0;
  const shown = query.data?.shown ?? rows.length;
  const badges = query.data?.badges;

  // Distinct sources present across the current rows — feeds the source multiselect.
  const availableSources = React.useMemo(() => {
    const s = new Set<string>();
    for (const r of rows) if (r.source) s.add(String(r.source));
    return Array.from(s).sort();
  }, [rows]);

  // ── selection + detail pane ──────────────────────────────────────────────────
  const [selectedId, setSelectedId] = React.useState<number | null>(null);
  const [detailOpen, setDetailOpen] = React.useState(true);
  const selectedRow = React.useMemo(
    () => rows.find((r) => r.id === selectedId) ?? null,
    [rows, selectedId],
  );

  // ── row windowing (client-side incremental reveal, no virtualization dep) ─────
  const [windowSize, setWindowSize] = React.useState(DEFAULT_PAGE_SIZE);
  React.useEffect(() => {
    // Reset the reveal window whenever the filtered result set changes.
    setWindowSize(DEFAULT_PAGE_SIZE);
  }, [params]);
  const visibleRows = React.useMemo(
    () => windowRows(rows, windowSize),
    [rows, windowSize],
  );
  const moreToLoad = hasMore(windowSize, rows.length);
  const sentinelRef = React.useRef<HTMLTableRowElement | null>(null);
  React.useEffect(() => {
    const el = sentinelRef.current;
    if (!el || !moreToLoad) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setWindowSize((w) => nextShown(w, rows.length));
        }
      },
      { rootMargin: "400px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [moreToLoad, rows.length]);

  // ── daily run + console ──────────────────────────────────────────────────────
  const [runJobId, setRunJobId] = React.useState<string | null>(null);
  const [consoleOpen, setConsoleOpen] = React.useState(false);
  const [running, setRunning] = React.useState(false);

  const startRun = React.useCallback(() => {
    setRunning(true);
    endpoints
      .startDailyRun()
      .then((r) => {
        setRunJobId(r.job_id);
        setConsoleOpen(true);
      })
      .catch((e) => {
        setRunning(false);
        if (e instanceof ApiError && e.status === 409) {
          const body = e.body as RunConflictBody | null;
          // Attach the console to the already-running job so the user sees it.
          if (body?.job_id) {
            setRunJobId(body.job_id);
            setConsoleOpen(true);
            setRunning(true);
          }
          toast("Already running", {
            description: e.message || "A run is already in progress.",
          });
        } else {
          toast.error("Couldn't start the run", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          });
        }
      });
  }, []);

  // ── triage actions ───────────────────────────────────────────────────────────
  const onTrack = React.useCallback(
    (row: InboxRow) => {
      track.mutate(row.id, {
        onSuccess: () =>
          toast.success("Tracked", {
            description: `${row.title} · ${row.company} moved to your tracker.`,
          }),
        onError: (e) =>
          toast.error("Couldn't track", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          }),
      });
      if (selectedId === row.id) setSelectedId(null);
    },
    [track, selectedId],
  );

  const undoToast = React.useCallback(
    (token: string | undefined, n: number) => {
      toast(`Dismissed ${n} job${n === 1 ? "" : "s"}`, {
        description: "Hidden from future runs.",
        action: {
          label: "Undo",
          onClick: () =>
            undoDismiss.mutate(token, {
              onSuccess: (r) =>
                toast.success("Restored", {
                  description: `${r.restored} job${r.restored === 1 ? "" : "s"} back in your inbox.`,
                }),
              onError: (e) =>
                toast.error("Couldn't undo", {
                  description:
                    e instanceof ApiError ? e.message : "Please try again.",
                }),
            }),
        },
      });
    },
    [undoDismiss],
  );

  const onDismiss = React.useCallback(
    (row: InboxRow) => {
      // Route single dismiss through the bulk endpoint so we always get an
      // undo_token back (the single /dismiss route doesn't stash for undo).
      dismissBulk.mutate([row.id], {
        onSuccess: (r) => undoToast(r.undo_token, r.dismissed || 1),
        onError: (e) =>
          toast.error("Couldn't dismiss", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          }),
      });
      if (selectedId === row.id) setSelectedId(null);
    },
    [dismissBulk, undoToast, selectedId],
  );

  const onOpen = React.useCallback((row: InboxRow) => {
    if (row.url) window.open(String(row.url), "_blank", "noopener,noreferrer");
  }, []);

  // ── bulk dismiss (all shown) ─────────────────────────────────────────────────
  const [confirmBulk, setConfirmBulk] = React.useState(false);
  const onDismissAllShown = React.useCallback(() => {
    const ids = rows.map((r) => r.id);
    if (ids.length === 0) return;
    dismissBulk.mutate(ids, {
      onSuccess: (r) => undoToast(r.undo_token, r.dismissed),
      onError: (e) =>
        toast.error("Couldn't dismiss", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
    });
    setSelectedId(null);
  }, [rows, dismissBulk, undoToast]);

  // Dismiss just a multi-selected range (Shift-click). Falls back to all-shown.
  const [rangeSelected, setRangeSelected] = React.useState<Set<number>>(
    () => new Set(),
  );
  const onDismissSelected = React.useCallback(() => {
    const ids = Array.from(rangeSelected);
    if (ids.length === 0) return;
    dismissBulk.mutate(ids, {
      onSuccess: (r) => undoToast(r.undo_token, r.dismissed),
      onError: (e) =>
        toast.error("Couldn't dismiss", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
    });
    setRangeSelected(new Set());
  }, [rangeSelected, dismissBulk, undoToast]);

  // ── palette commands (registered while the tab is mounted) ───────────────────
  const paletteCommands = React.useMemo<AppCommand[]>(
    () => [
      {
        id: "update-now",
        label: "Update my Inbox now",
        icon: RefreshCw,
        run: startRun,
      },
      {
        id: "dismiss-shown",
        label: "Dismiss all shown jobs",
        icon: XCircle,
        run: () => setConfirmBulk(true),
      },
    ],
    [startRun],
  );
  useRegisterCommands("inbox", paletteCommands);

  const onSearchDebounced = React.useCallback((q: string) => {
    setFilters((f) => (f.q === q ? f : { ...f, q }));
  }, []);

  const hasSelection = rangeSelected.size > 0;

  return (
    <section aria-labelledby="inbox-heading" className="flex h-full flex-col">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1
            id="inbox-heading"
            className="zg-serif text-foreground flex items-center gap-2.5 text-2xl font-semibold tracking-tight"
          >
            <Inbox className="text-primary size-6" strokeWidth={2} />
            Inbox
          </h1>
          <p className="text-muted-foreground max-w-xl text-sm leading-relaxed">
            Every match, ready to triage. <Kbd>t</Kbd> track, <Kbd>d</Kbd>{" "}
            dismiss, <Kbd>o</Kbd> open on the focused row — or use the buttons.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <AiMenu filters={filters} />
          <Button onClick={startRun} disabled={running}>
            {running ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <RefreshCw className="size-4" />
            )}
            Update my Inbox now
          </Button>
        </div>
      </div>

      <InboxBadges badges={badges} />

      <InboxFilterBar
        state={filters}
        onChange={setFilters}
        availableSources={availableSources}
        onSearchDebounced={onSearchDebounced}
        summary={shownSummary(visibleRows.length, shown, total)}
      />

      {/* Bulk action bar (shown when there's a selection OR any rows to dismiss) */}
      {rows.length > 0 && (
        <div className="mt-3 flex items-center gap-2">
          {hasSelection ? (
            <>
              <span className="text-muted-foreground zg-num text-xs">
                {rangeSelected.size} selected
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={onDismissSelected}
                className="text-muted-foreground hover:text-destructive"
              >
                <XCircle className="size-3.5" />
                Dismiss selected
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setRangeSelected(new Set())}
              >
                Clear
              </Button>
            </>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setConfirmBulk(true)}
              className="text-muted-foreground hover:text-destructive"
            >
              <XCircle className="size-3.5" />
              Dismiss all shown
            </Button>
          )}
          <button
            type="button"
            onClick={() => setDetailOpen((o) => !o)}
            className="text-muted-foreground hover:text-foreground ml-auto hidden items-center gap-1.5 text-xs lg:inline-flex"
          >
            {detailOpen ? (
              <>
                <PanelRightClose className="size-3.5" /> Hide details
              </>
            ) : (
              <>
                <PanelRightOpen className="size-3.5" /> Show details
              </>
            )}
          </button>
        </div>
      )}

      {/* Split body */}
      <div className="mt-4 flex min-h-0 flex-1 gap-4">
        <div
          className={cn(
            "min-w-0 flex-1",
            detailOpen && "lg:max-w-[calc(100%-24rem)]",
          )}
        >
          {query.isLoading ? (
            <div className="border-border bg-card rounded-lg border p-2">
              <TableSkeleton rows={10} />
            </div>
          ) : query.isError ? (
            <ErrorState
              title="Couldn't load your Inbox"
              message={
                query.error instanceof ApiError
                  ? query.error.message
                  : "The inbox service didn't respond."
              }
              onRetry={() => query.refetch()}
            />
          ) : rows.length === 0 ? (
            <InboxEmpty
              filtered={total > 0}
              onClearFilters={() => setFilters(makeDefaultFilters())}
              onUpdate={startRun}
            />
          ) : (
            <InboxTable
              rows={visibleRows}
              totalRows={rows.length}
              selectedId={selectedId}
              onSelect={(id) => {
                setSelectedId(id);
                if (!detailOpen) setDetailOpen(true);
              }}
              rangeSelected={rangeSelected}
              onRangeChange={setRangeSelected}
              onTrack={onTrack}
              onDismiss={onDismiss}
              onOpen={onOpen}
              moreToLoad={moreToLoad}
              sentinelRef={sentinelRef}
            />
          )}
        </div>

        {/* Detail rail — collapsible on large screens; on small screens it stacks */}
        {detailOpen && rows.length > 0 && (
          <aside className="border-border bg-card hidden w-96 shrink-0 rounded-lg border lg:block">
            <InboxDetail
              row={selectedRow}
              onTrack={onTrack}
              onDismiss={onDismiss}
              onOpen={onOpen}
            />
          </aside>
        )}
      </div>

      {/* Run console drawer */}
      <RunConsole
        jobId={runJobId}
        open={consoleOpen}
        onOpenChange={setConsoleOpen}
        onTerminal={() => setRunning(false)}
      />

      <ConfirmDialog
        open={confirmBulk}
        onOpenChange={setConfirmBulk}
        title="Dismiss all shown jobs?"
        description={`${rows.length} job${rows.length === 1 ? "" : "s"} in the current view will be hidden from future runs. You can undo right after.`}
        confirmLabel="Dismiss all"
        cancelLabel="Cancel"
        onConfirm={onDismissAllShown}
      />
    </section>
  );
}

// ── the table ─────────────────────────────────────────────────────────────────

interface InboxTableProps {
  rows: InboxRow[];
  totalRows: number;
  selectedId: number | null;
  onSelect: (id: number) => void;
  rangeSelected: Set<number>;
  onRangeChange: (next: Set<number>) => void;
  onTrack: (row: InboxRow) => void;
  onDismiss: (row: InboxRow) => void;
  onOpen: (row: InboxRow) => void;
  moreToLoad: boolean;
  sentinelRef: React.RefObject<HTMLTableRowElement | null>;
}

function InboxTable({
  rows,
  selectedId,
  onSelect,
  rangeSelected,
  onRangeChange,
  onTrack,
  onDismiss,
  onOpen,
  moreToLoad,
  sentinelRef,
}: InboxTableProps) {
  const [focused, setFocused] = React.useState(0);
  const rowRefs = React.useRef<(HTMLTableRowElement | null)[]>([]);
  const lastClicked = React.useRef<number | null>(null);

  React.useEffect(() => {
    if (focused > rows.length - 1) setFocused(Math.max(0, rows.length - 1));
  }, [rows.length, focused]);

  const focusRow = (i: number) => {
    const clamped = Math.max(0, Math.min(rows.length - 1, i));
    setFocused(clamped);
    rowRefs.current[clamped]?.focus();
  };

  const onRowKeyDown = (e: React.KeyboardEvent, row: InboxRow, i: number) => {
    switch (e.key.toLowerCase()) {
      case "t":
        e.preventDefault();
        onTrack(row);
        break;
      case "d":
        e.preventDefault();
        onDismiss(row);
        break;
      case "o":
        e.preventDefault();
        onOpen(row);
        break;
      case "enter":
        e.preventDefault();
        onSelect(row.id);
        break;
      case "arrowdown":
        e.preventDefault();
        focusRow(i + 1);
        break;
      case "arrowup":
        e.preventDefault();
        focusRow(i - 1);
        break;
      default:
        break;
    }
  };

  // Shift-click range select over the currently-rendered rows.
  const onRowClick = (e: React.MouseEvent, index: number, row: InboxRow) => {
    if (e.shiftKey && lastClicked.current !== null) {
      e.preventDefault();
      const [a, b] = [lastClicked.current, index].sort((x, y) => x - y);
      const next = new Set(rangeSelected);
      for (let k = a; k <= b; k++) {
        const id = rows[k]?.id;
        if (id !== undefined) next.add(id);
      }
      onRangeChange(next);
    } else {
      lastClicked.current = index;
      onSelect(row.id);
    }
  };

  return (
    <div className="border-border bg-card overflow-hidden rounded-lg border">
      <div className="relative w-full overflow-x-auto">
        <table className="w-full caption-bottom text-sm">
          <thead className="[&_tr]:border-b">
            <tr className="border-border/70 border-b">
              <Th className="w-16 text-center">Fit</Th>
              <Th className="min-w-[15rem]">Role</Th>
              <Th className="hidden md:table-cell">Location</Th>
              <Th className="zg-num hidden text-right lg:table-cell">Salary</Th>
              <Th className="hidden sm:table-cell">Source</Th>
              <Th className="hidden text-right xl:table-cell">Posted</Th>
              <Th className="w-[8.5rem] text-right">Actions</Th>
            </tr>
          </thead>
          <tbody className="[&_tr:last-child]:border-0">
            {rows.map((row, i) => {
              const isSelected = row.id === selectedId;
              const isChecked = rangeSelected.has(row.id);
              return (
                <tr
                  key={row.id}
                  ref={(el) => {
                    rowRefs.current[i] = el;
                  }}
                  tabIndex={i === focused ? 0 : -1}
                  onFocus={() => setFocused(i)}
                  onKeyDown={(e) => onRowKeyDown(e, row, i)}
                  onClick={(e) => onRowClick(e, i, row)}
                  aria-selected={isSelected}
                  aria-label={`${row.title} at ${row.company}`}
                  className={cn(
                    "group border-border/70 hover:bg-secondary/45 cursor-pointer border-b transition-colors outline-none",
                    "focus-visible:bg-secondary/50 focus-visible:ring-ring/40 focus-visible:ring-2 focus-visible:ring-inset",
                    isSelected && "bg-accent/60 hover:bg-accent/60",
                    isChecked && "bg-primary/8",
                  )}
                >
                  <td className="px-3 py-2.5 text-center align-middle">
                    <ScoreChip value={fitValue(row)} />
                  </td>
                  <td className="px-3 py-2.5 align-middle">
                    <div className="flex items-center gap-2">
                      {row.computed.is_new && (
                        <span
                          title="New in the latest run"
                          aria-label="New"
                          className="bg-primary size-2 shrink-0 rounded-full"
                        />
                      )}
                      <div className="flex min-w-0 flex-col gap-0.5">
                        <span className="text-foreground truncate leading-snug font-medium">
                          {row.title || "Untitled role"}
                        </span>
                        <span className="text-muted-foreground truncate text-xs">
                          {row.company || "Unknown company"}
                        </span>
                      </div>
                    </div>
                  </td>
                  <td className="text-muted-foreground hidden px-3 py-2.5 align-middle text-sm md:table-cell">
                    <span className="inline-flex items-center gap-1.5">
                      <span className="truncate">{row.location || "—"}</span>
                      {isRemote(row) && (
                        <span className="border-primary/40 bg-primary/10 text-primary rounded-[var(--radius-chip)] border px-1 py-0.5 text-[0.65rem] font-medium">
                          Remote
                        </span>
                      )}
                    </span>
                  </td>
                  <td className="zg-num text-muted-foreground hidden px-3 py-2.5 text-right align-middle text-xs lg:table-cell">
                    {row.salary_text || "—"}
                  </td>
                  <td className="text-muted-foreground hidden px-3 py-2.5 align-middle text-xs capitalize sm:table-cell">
                    {row.source || "—"}
                  </td>
                  <td className="zg-num text-muted-foreground hidden px-3 py-2.5 text-right align-middle text-xs xl:table-cell">
                    {postedLabel(row)}
                  </td>
                  <td className="px-3 py-2.5 text-right align-middle">
                    <RowActions
                      row={row}
                      onTrack={onTrack}
                      onDismiss={onDismiss}
                      onOpen={onOpen}
                    />
                  </td>
                </tr>
              );
            })}

            {moreToLoad && (
              <tr ref={sentinelRef} aria-hidden>
                <td colSpan={7} className="px-3 py-4 text-center">
                  <span className="text-muted-foreground inline-flex items-center gap-2 text-xs">
                    <Loader2 className="size-3.5 animate-spin" />
                    Loading more…
                  </span>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Th({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <th
      className={cn(
        "text-muted-foreground h-10 px-3 text-left align-middle text-xs font-semibold tracking-wide uppercase whitespace-nowrap",
        className,
      )}
    >
      {children}
    </th>
  );
}

function RowActions({
  row,
  onTrack,
  onDismiss,
  onOpen,
}: {
  row: InboxRow;
  onTrack: (r: InboxRow) => void;
  onDismiss: (r: InboxRow) => void;
  onOpen: (r: InboxRow) => void;
}) {
  return (
    <div
      className="flex items-center justify-end gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 focus-within:opacity-100"
      onClick={(e) => e.stopPropagation()}
    >
      <IconAction
        label="Track (t)"
        onClick={() => onTrack(row)}
        icon={<CheckCircle2 className="size-4" />}
        tone="success"
      />
      <IconAction
        label="Dismiss (d)"
        onClick={() => onDismiss(row)}
        icon={<XCircle className="size-4" />}
        tone="danger"
      />
      <IconAction
        label="Open (o)"
        onClick={() => onOpen(row)}
        icon={<ExternalLink className="size-4" />}
        tone="muted"
        disabled={!row.url}
      />
    </div>
  );
}

function IconAction({
  label,
  onClick,
  icon,
  tone,
  disabled,
}: {
  label: string;
  onClick: () => void;
  icon: React.ReactNode;
  tone: "success" | "danger" | "muted";
  disabled?: boolean;
}) {
  const toneCls =
    tone === "success"
      ? "hover:text-[var(--zg-success)]"
      : tone === "danger"
        ? "hover:text-destructive"
        : "hover:text-primary";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          tabIndex={-1}
          disabled={disabled}
          onClick={onClick}
          aria-label={label}
          className={cn("text-muted-foreground size-8", toneCls)}
        >
          {icon}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

function InboxEmpty({
  filtered,
  onClearFilters,
  onUpdate,
}: {
  filtered: boolean;
  onClearFilters: () => void;
  onUpdate: () => void;
}) {
  // Two empties: filters hid everything (offer Clear) vs. a genuinely empty inbox
  // (offer Update). Inclusion over precision: when filters are the cause, never
  // imply there are no jobs — point at the filters.
  if (filtered) {
    return (
      <EmptyState
        icon={Inbox}
        title="No jobs match these filters"
        message="Your filters are hiding every job in the inbox. Loosen them to see more — nothing was deleted."
        action={{ label: "Clear filters", onClick: onClearFilters }}
      />
    );
  }
  return (
    <EmptyState
      icon={Inbox}
      title="Your inbox is empty"
      message="Run a search to fill your inbox with fresh matches, then triage them here."
      action={{ label: "Update my Inbox now", onClick: onUpdate }}
    />
  );
}

// ── row helpers ────────────────────────────────────────────────────────────────

/** Lead with the AI fit; fall back to the base score (never empty for a scored
 * row). Same rule as Top Picks + the detail pane. */
function fitValue(row: InboxRow): number | null | undefined {
  const fit = row.fit;
  if (typeof fit === "number" && fit >= 0) return fit;
  return row.score;
}

/** Heuristic remote badge from the location text — presentational only, never a
 * filter (the Location mode filter is the real control). */
function isRemote(row: InboxRow): boolean {
  const loc = (row.location || "").toLowerCase();
  return loc.includes("remote") || loc.includes("anywhere");
}

/** A compact posted label from `created` (falls back to date_added), shown as a
 * relative age. Blank → "—". */
function postedLabel(row: InboxRow): string {
  const raw = String(row.created || row.date_added || "").trim();
  if (!raw) return "—";
  const t = Date.parse(raw);
  if (Number.isNaN(t)) return raw;
  const days = Math.floor((Date.now() - t) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "1d";
  if (days < 30) return `${days}d`;
  const months = Math.floor(days / 30);
  return `${months}mo`;
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="border-border bg-secondary text-foreground zg-num mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded border px-1 text-[0.7rem]">
      {children}
    </kbd>
  );
}
