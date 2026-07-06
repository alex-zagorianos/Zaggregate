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
  ChevronDown,
  Zap,
  Layers,
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
  type DailyRunKnobs,
  type InboxRow,
  type RunConflictBody,
} from "@/api/client";
import {
  makeDefaultFilters,
  toParams,
  filtersToUrlParams,
  filtersFromUrlParams,
  type InboxFilterState,
} from "@/lib/inbox-filter-state";
import { useUrlSyncedState } from "@/lib/useUrlSyncedState";
import {
  DEFAULT_PAGE_SIZE,
  hasMore,
  nextShown,
  windowRows,
  shownSummary,
} from "@/lib/window-rows";
import { useRegisterCommands, type AppCommand } from "@/lib/app-commands";
import { takeInboxRunJob } from "@/lib/inbox-run-handoff";
import { postedLabel as postedLabelFromDate } from "@/lib/relative-time";
import { ScoreChip } from "@/components/score-chip";
import { GhostRowBadge } from "@/components/ghost-row-badge";
import { EmptyState, TableSkeleton, useQueryGuard } from "@/components/states";
import { ShortcutHint } from "@/components/kbd";
import { TriageActions } from "@/components/row-actions";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

import { InboxFilterBar } from "./InboxFilterBar";
import { InboxBadges } from "./InboxBadges";
import { NewSinceVisitBanner } from "./NewSinceVisitBanner";
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
  // URL-synced filter state (KNOWN_ISSUES: "Filter state not URL-synced — back/
  // refresh resets the Inbox view"). URL wins on mount; every change thereafter is
  // mirrored back with replaceState (debounced) so typing doesn't spam history and
  // refresh/back/forward reload the same view.
  useUrlSyncedState<InboxFilterState>({
    state: filters,
    setState: setFilters,
    serialize: filtersToUrlParams,
    deserialize: filtersFromUrlParams,
  });
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

  // AI-first setup handoff (S40): the onboarding wizard may have started a
  // first-run job and stashed its id for us (the same sessionStorage pattern
  // Discover uses to hand keywords to Search). Consume-and-clear on mount and
  // attach the run console to it, so the user lands here watching their first
  // search stream in — zero extra clicks. Runs once.
  React.useEffect(() => {
    const jobId = takeInboxRunJob();
    if (jobId) {
      setRunJobId(jobId);
      setConsoleOpen(true);
      setRunning(true);
    }
  }, []);

  // `knobs` is the optional run-shaping body (S36 parity gap P1). The knobless
  // `startRun` wrapper below is what buttons/palette/empty-state bind to, so a
  // MouseEvent can never leak in as the knobs object.
  const startRunWith = React.useCallback((knobs?: DailyRunKnobs) => {
    setRunning(true);
    endpoints
      .startDailyRun(knobs)
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

  const startRun = React.useCallback(() => startRunWith(), [startRunWith]);

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

  const guard = useQueryGuard(query, {
    title: "Couldn't load your Inbox",
    fallback: "The inbox service didn't respond.",
    loading: (
      <div className="border-border bg-card rounded-lg border p-2">
        <TableSkeleton rows={10} />
      </div>
    ),
  });

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
            <ShortcutHint
              lead="Every match, ready to triage."
              actions={[
                { key: "t", label: "track" },
                { key: "d", label: "dismiss" },
                { key: "o", label: "open" },
              ]}
              tail="on the focused row — or use the buttons."
            />
          </p>
        </div>
        <div className="flex items-center gap-2">
          <AiMenu filters={filters} />
          {/* Split button: the main action keeps the engine-default run; the
              chevron offers run depth (S36 parity gap P1 — CLI --max-pages). */}
          <div className="flex items-center">
            <Button
              onClick={startRun}
              disabled={running}
              className="rounded-r-none"
            >
              {running ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <RefreshCw className="size-4" />
              )}
              Update my Inbox now
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  disabled={running}
                  size="icon"
                  aria-label="Run options"
                  className="border-primary-foreground/20 rounded-l-none border-l"
                >
                  <ChevronDown className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="min-w-[16rem]">
                <DropdownMenuLabel>Run depth</DropdownMenuLabel>
                <DropdownMenuItem
                  onSelect={() => startRunWith({ max_pages: 1 })}
                >
                  <Zap className="size-4 opacity-70" />
                  <div className="flex flex-col">
                    <span>Quick run</span>
                    <span className="text-muted-foreground text-xs">
                      1 page per source — fastest, fewest calls
                    </span>
                  </div>
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => startRunWith()}>
                  <RefreshCw className="size-4 opacity-70" />
                  <div className="flex flex-col">
                    <span>Standard run</span>
                    <span className="text-muted-foreground text-xs">
                      2 pages per source — the default
                    </span>
                  </div>
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={() => startRunWith({ max_pages: 3 })}
                >
                  <Layers className="size-4 opacity-70" />
                  <div className="flex flex-col">
                    <span>Deep run</span>
                    <span className="text-muted-foreground text-xs">
                      3 pages per source — widest net, slowest
                    </span>
                  </div>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </div>

      <InboxBadges badges={badges} />

      <NewSinceVisitBanner rows={rows} />

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
          {guard ??
            (rows.length === 0 ? (
              <InboxEmpty
                filtered={total > 0}
                running={running}
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
            ))}
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
  const prevLen = React.useRef(rows.length);
  // Whether a table row currently owns keyboard focus — the gate for re-homing
  // focus after a triage removal (below). Kept in a ref so reading it in the layout
  // effect sees the value as of the last focus/blur, not a stale render closure.
  const rowHadFocus = React.useRef(false);

  React.useEffect(() => {
    if (focused > rows.length - 1) setFocused(Math.max(0, rows.length - 1));
  }, [rows.length, focused]);

  // Keyboard-first triage: after a t/d action optimistically removes the focused
  // row, its <tr> unmounts and DOM focus falls back to <body>, dead-ending the
  // rapid-fire d,d,d flow. When the row count SHRINKS and a row HAD keyboard focus
  // (so this is a triage removal, not filtering/windowing or a mouse action), re-home
  // focus to the row now at the same index (clamped to the new last row) so the next
  // ArrowDown/t/d lands. useLayoutEffect so the refocus happens before paint (no
  // visible focus-ring flicker). Only acts when nothing in the table already holds
  // focus, so it never yanks focus off a control the user just tabbed to.
  React.useLayoutEffect(() => {
    const shrank = rows.length < prevLen.current;
    prevLen.current = rows.length;
    if (!shrank || rows.length === 0 || !rowHadFocus.current) return;
    const active = document.activeElement;
    const focusInTable = rowRefs.current.some((el) => el && el === active);
    if (focusInTable) return; // a row already has focus — don't yank it
    const idx = Math.max(0, Math.min(rows.length - 1, focused));
    rowRefs.current[idx]?.focus();
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
                  onFocus={() => {
                    setFocused(i);
                    rowHadFocus.current = true;
                  }}
                  onBlur={(e) => {
                    // Focus left this row; only mark the table as unfocused if it
                    // didn't move to another row (a removal unmounts the row with no
                    // relatedTarget, which we WANT to treat as still-in-triage).
                    const next = e.relatedTarget as Node | null;
                    if (next && rowRefs.current.some((el) => el === next))
                      return;
                    if (next) rowHadFocus.current = false;
                  }}
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
                        <span className="flex items-center gap-1.5">
                          <span className="text-foreground truncate leading-snug font-medium">
                            {row.title || "Untitled role"}
                          </span>
                          <GhostRowBadge ghost={row.ghost} />
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
    <TriageActions
      actions={[
        {
          key: "track",
          label: "Track (t)",
          onClick: () => onTrack(row),
          icon: <CheckCircle2 className="size-4" />,
          tone: "success",
        },
        {
          key: "dismiss",
          label: "Dismiss (d)",
          onClick: () => onDismiss(row),
          icon: <XCircle className="size-4" />,
          tone: "danger",
        },
        {
          key: "open",
          label: "Open (o)",
          onClick: () => onOpen(row),
          icon: <ExternalLink className="size-4" />,
          tone: "muted",
          disabled: !row.url,
        },
      ]}
    />
  );
}

function InboxEmpty({
  filtered,
  running,
  onClearFilters,
  onUpdate,
}: {
  filtered: boolean;
  running: boolean;
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
  // A run is in flight but nothing's landed yet — set the wait expectation warmly
  // instead of offering another "Update" (which would just conflict).
  if (running) {
    return (
      <EmptyState
        icon={Loader2}
        iconClassName="animate-spin"
        title="Finding your first matches…"
        message="Your first results land when the run finishes — usually a few minutes on a quick pass. You can keep working while it runs."
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

/** The Posted column's label: `created` falls back to `date_added`, formatted
 * as a relative age by the shared lib/relative-time helper. */
function postedLabel(row: InboxRow): string {
  return postedLabelFromDate(row.created || row.date_added);
}
