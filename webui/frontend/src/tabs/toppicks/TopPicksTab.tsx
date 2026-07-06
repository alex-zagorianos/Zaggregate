import * as React from "react";
import { toast } from "sonner";
import {
  useReactTable,
  getCoreRowModel,
  type ColumnDef,
} from "@tanstack/react-table";
import {
  Star,
  Inbox,
  Sparkles,
  ExternalLink,
  CheckCircle2,
  XCircle,
  ArrowUpRight,
} from "lucide-react";

import { useTopPicks, useTrackInbox, useDismissInbox } from "@/api/queries";
import type { TopPickRow, TopPicksLimit } from "@/api/client";
import { ScoreChip } from "@/components/score-chip";
import { EmptyState, TableSkeleton, useQueryGuard } from "@/components/states";
import { ShortcutHint } from "@/components/kbd";
import { TriageActions } from "@/components/row-actions";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Select } from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ApiError } from "@/api/client";

/* Top Picks — the AI recommendation shortlist over the inbox.
 *
 * Read-only ranked table with per-row triage: Track (promote to the tracker),
 * Dismiss (hide), Open (external). Track/Dismiss are optimistic (the row leaves
 * immediately, rolls back on error) with a sonner toast. Keyboard: focus a row
 * and press t / d / o. "Show top N" maps straight to the engine's top_picks
 * limit ("All" = every ranked row). */

const LIMIT_OPTIONS: { value: string; label: string }[] = [
  { value: "10", label: "Top 10" },
  { value: "15", label: "Top 15" },
  { value: "20", label: "Top 20" },
  { value: "25", label: "Top 25" },
  { value: "50", label: "Top 50" },
  { value: "all", label: "All" },
];

function parseLimit(raw: string): TopPicksLimit {
  return raw === "all" ? "all" : Number(raw);
}

/** The AI fit is the re-rank signal we lead with; fall back to the base match
 * score when a row hasn't been fit-scored yet, so the chip is never empty for a
 * scored row. */
function fitValue(row: TopPickRow): number | null | undefined {
  const fit = row.fit;
  if (typeof fit === "number" && fit >= 0) return fit;
  return row.score;
}

export function TopPicksTab() {
  const [limitRaw, setLimitRaw] = React.useState("15");
  const limit = parseLimit(limitRaw);
  const query = useTopPicks(limit);
  const track = useTrackInbox();
  const dismiss = useDismissInbox();

  const rows = query.data?.rows ?? [];

  const onTrack = React.useCallback(
    (row: TopPickRow) => {
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
    },
    [track],
  );

  const onDismiss = React.useCallback(
    (row: TopPickRow) => {
      dismiss.mutate(row.id, {
        onSuccess: () =>
          toast("Dismissed", {
            description: `${row.title} · ${row.company} hidden from future runs.`,
          }),
        onError: (e) =>
          toast.error("Couldn't dismiss", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          }),
      });
    },
    [dismiss],
  );

  const onOpen = React.useCallback((row: TopPickRow) => {
    if (row.url) window.open(row.url, "_blank", "noopener,noreferrer");
  }, []);

  const guard = useQueryGuard(query, {
    title: "Couldn't load your Top Picks",
    fallback: "The recommendation service didn't respond.",
    loading: (
      <div className="mt-6 rounded-lg border border-border bg-card p-2">
        <TableSkeleton rows={8} />
      </div>
    ),
  });

  return (
    <section aria-labelledby="toppicks-heading">
      <Header
        limitRaw={limitRaw}
        onLimitChange={setLimitRaw}
        count={rows.length}
      />

      {guard ??
        (rows.length === 0 ? (
          <TopPicksEmpty />
        ) : (
          <PicksTable
            rows={rows}
            onTrack={onTrack}
            onDismiss={onDismiss}
            onOpen={onOpen}
          />
        ))}
    </section>
  );
}

function Header({
  limitRaw,
  onLimitChange,
  count,
}: {
  limitRaw: string;
  onLimitChange: (v: string) => void;
  count: number;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="space-y-1">
        <h1
          id="toppicks-heading"
          className="zg-serif text-foreground flex items-center gap-2.5 text-2xl font-semibold tracking-tight"
        >
          <Star className="text-primary size-6" strokeWidth={2} />
          Top Picks
        </h1>
        <p className="text-muted-foreground max-w-xl text-sm leading-relaxed">
          <ShortcutHint
            lead="Your AI-ranked shortlist."
            verb="Triage with"
            actions={[
              { key: "t", label: "track" },
              { key: "d", label: "dismiss" },
              { key: "o", label: "open" },
            ]}
            tail="— or the row buttons."
          />
        </p>
      </div>
      <div className="flex items-center gap-2">
        {count > 0 && (
          <span className="text-muted-foreground hidden text-xs sm:inline">
            <span className="zg-num">{count}</span> shown
          </span>
        )}
        <label className="text-muted-foreground text-sm">Show</label>
        <Select
          aria-label="How many top picks to show"
          value={limitRaw}
          onChange={(e) => onLimitChange(e.target.value)}
          className="w-[7.5rem]"
        >
          {LIMIT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
      </div>
    </div>
  );
}

// TanStack Table column defs. We drive the data through the headless row model
// (getCoreRowModel) for the ranked list; rendering + the roving-focus keyboard
// layer stay bespoke because a fixed 6-column triage table needs no sorting/
// virtualization but DOES need t/d/o key handling TanStack doesn't provide.
const COLUMNS: ColumnDef<TopPickRow>[] = [
  { id: "rank", accessorKey: "rank" },
  { id: "role", accessorKey: "title" },
  { id: "location", accessorKey: "location" },
  { id: "fit", accessorFn: (r) => fitValue(r) },
  { id: "why", accessorKey: "fit_why" },
  { id: "actions" },
];

function PicksTable({
  rows,
  onTrack,
  onDismiss,
  onOpen,
}: {
  rows: TopPickRow[];
  onTrack: (r: TopPickRow) => void;
  onDismiss: (r: TopPickRow) => void;
  onOpen: (r: TopPickRow) => void;
}) {
  const table = useReactTable({
    data: rows,
    columns: COLUMNS,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (r) => String(r.id),
  });
  const tableRows = table.getRowModel().rows;

  // Roving focus: the focused row index owns tabindex=0; the rest are -1. Arrow
  // keys move focus; t/d/o act on the focused row.
  const [focused, setFocused] = React.useState(0);
  const rowRefs = React.useRef<(HTMLTableRowElement | null)[]>([]);

  React.useEffect(() => {
    if (focused > tableRows.length - 1)
      setFocused(Math.max(0, tableRows.length - 1));
  }, [tableRows.length, focused]);

  const focusRow = (i: number) => {
    const clamped = Math.max(0, Math.min(tableRows.length - 1, i));
    setFocused(clamped);
    rowRefs.current[clamped]?.focus();
  };

  const onRowKeyDown = (e: React.KeyboardEvent, row: TopPickRow, i: number) => {
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

  return (
    <div className="mt-6 overflow-hidden rounded-lg border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-14 text-center">#</TableHead>
            <TableHead className="min-w-[16rem]">Role</TableHead>
            <TableHead className="hidden md:table-cell">Location</TableHead>
            <TableHead className="w-20 text-center">Fit</TableHead>
            <TableHead className="hidden lg:table-cell">Why</TableHead>
            <TableHead className="w-[8.5rem] text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {tableRows.map((tr, i) => {
            const row = tr.original;
            return (
              <TableRow
                key={row.id}
                ref={(el) => {
                  rowRefs.current[i] = el;
                }}
                tabIndex={i === focused ? 0 : -1}
                onFocus={() => setFocused(i)}
                onKeyDown={(e) => onRowKeyDown(e, row, i)}
                aria-label={`Rank ${row.rank}: ${row.title} at ${row.company}`}
                className="group cursor-default"
              >
                <TableCell className="text-center">
                  <span className="zg-num text-muted-foreground text-base font-semibold tabular-nums">
                    {row.rank}
                  </span>
                </TableCell>

                <TableCell>
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <span className="text-foreground truncate leading-snug font-medium">
                      {row.title || "Untitled role"}
                    </span>
                    <span className="text-muted-foreground truncate text-xs">
                      {row.company || "Unknown company"}
                    </span>
                  </div>
                </TableCell>

                <TableCell className="hidden md:table-cell">
                  <span className="text-muted-foreground text-sm">
                    {row.location || "—"}
                  </span>
                </TableCell>

                <TableCell className="text-center">
                  <ScoreChip value={fitValue(row)} />
                </TableCell>

                <TableCell className="hidden max-w-[22rem] lg:table-cell">
                  <WhyCell why={row.fit_why} />
                </TableCell>

                <TableCell className="text-right">
                  <RowActions
                    row={row}
                    onTrack={onTrack}
                    onDismiss={onDismiss}
                    onOpen={onOpen}
                  />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

function WhyCell({ why }: { why: string | null | undefined }) {
  const text = (why ?? "").trim();
  if (!text) return <span className="text-muted-foreground/60 text-sm">—</span>;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <p className="text-muted-foreground line-clamp-2 cursor-help text-sm leading-snug">
          {text}
        </p>
      </TooltipTrigger>
      <TooltipContent className="max-w-sm text-sm leading-relaxed">
        {text}
      </TooltipContent>
    </Tooltip>
  );
}

function RowActions({
  row,
  onTrack,
  onDismiss,
  onOpen,
}: {
  row: TopPickRow;
  onTrack: (r: TopPickRow) => void;
  onDismiss: (r: TopPickRow) => void;
  onOpen: (r: TopPickRow) => void;
}) {
  // Actions live behind a hover/focus reveal so the table reads calm at rest,
  // but stay keyboard-reachable (focus-within opacity). tabIndex -1 keeps them
  // out of the row's own tab-stop; the roving row + t/d/o keys are the primary
  // path, buttons are the pointer path.
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
      stopPropagation={false}
    />
  );
}

function TopPicksEmpty() {
  return (
    <EmptyState
      icon={Star}
      title="No picks yet"
      message="Top Picks is your AI-ranked shortlist. Export your Inbox for AI ranking, paste the results back, and your shortlist lands here — ranked, with a reason for each."
    >
      <ByoAiFlow />
    </EmptyState>
  );
}

/* A subtle three-step illustration of the BYO-AI loop, built from the inbox /
 * sparkles / star lucide icons — atmosphere for the empty state, per the design
 * bar (guidance, not a blank slate). Rendered as children of EmptyState. */
function ByoAiFlow() {
  return (
    <div className="text-muted-foreground/80 mt-7 flex items-center gap-3 text-xs">
      <FlowStep icon={<Inbox className="size-4" />} label="Export inbox" />
      <FlowArrow />
      <FlowStep icon={<Sparkles className="size-4" />} label="AI ranks it" />
      <FlowArrow />
      <FlowStep icon={<Star className="size-4" />} label="Shortlist here" />
    </div>
  );
}

function FlowStep({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="border-border/70 bg-card flex items-center gap-2 rounded-full border px-3 py-1.5">
      <span className="text-primary/80">{icon}</span>
      <span>{label}</span>
    </div>
  );
}

function FlowArrow() {
  return <ArrowUpRight className="text-muted-foreground/40 size-4 rotate-45" />;
}
