import * as React from "react";
import { toast } from "sonner";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from "@tanstack/react-table";
import {
  ListChecks,
  Plus,
  Pencil,
  ExternalLink,
  Archive,
  ArchiveRestore,
  Trash2,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Bell,
} from "lucide-react";

import {
  useApplications,
  useSetApplicationStatus,
  useArchiveApplication,
  useRestoreApplication,
  useDeleteApplication,
} from "@/api/queries";
import { ApiError, type AppRow } from "@/api/client";
import {
  statusLabel,
  statusChipStyle,
  statusChipBorderTint,
} from "@/lib/status";
import { StatusChip } from "@/components/status-chip";
import { JobDialog } from "@/components/job-dialog";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";

/* Tracker — the application table, the web twin of ui/tab_tracker + the tk
 * TrackerTab. A chip-bar of status filters (All + each status + Archive) with
 * live counts drives the view; the table sorts by column and renders status as a
 * colored chip with an inline quick-status select; a follow-up-due dot flags rows
 * whose follow_up_date has arrived. Row actions differ by view: active rows Edit /
 * Open / Archive; archive-view rows Restore / Delete (confirmed). "+ Add job"
 * opens the JobDialog in create mode. Inclusion-over-precision: the table never
 * hides a row — filtering is the only drop, and it's the user's choice. */

const columnHelper = createColumnHelper<AppRow>();

/** Today as YYYY-MM-DD (local) for the follow-up-due comparison. */
function todayIso(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** A follow-up is "due" when it's set and on/before today. */
function isFollowupDue(row: AppRow, today: string): boolean {
  const f = (row.follow_up_date ?? "").trim();
  return !!f && f <= today;
}

export function TrackerTab() {
  // The active chip: "all" | "archived" | a specific status. Drives the query.
  const [view, setView] = React.useState<string>("all");
  const query = useApplications(view === "all" ? undefined : view);
  const rows = query.data?.rows ?? [];
  const counts = query.data?.counts ?? {};
  const followupsDue = query.data?.followups_due ?? 0;
  const labels = React.useMemo(() => STATIC_LABELS, []);
  const isArchive = view === "archived";

  // JobDialog state (null id = create).
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [editId, setEditId] = React.useState<number | null>(null);

  const openCreate = () => {
    setEditId(null);
    setDialogOpen(true);
  };
  const openEdit = (id: number) => {
    setEditId(id);
    setDialogOpen(true);
  };

  return (
    <section aria-labelledby="tracker-heading">
      <Header
        followupsDue={followupsDue}
        onAdd={openCreate}
        total={counts.all ?? 0}
      />

      <FilterBar view={view} onView={setView} counts={counts} labels={labels} />

      <div className="mt-5">
        {query.isLoading ? (
          <div className="rounded-lg border border-border bg-card p-2">
            <TableSkeleton rows={8} />
          </div>
        ) : query.isError ? (
          <ErrorState
            title="Couldn't load your applications"
            message={
              query.error instanceof ApiError
                ? query.error.message
                : "The tracker service didn't respond."
            }
            onRetry={() => query.refetch()}
          />
        ) : rows.length === 0 ? (
          <TrackerEmpty view={view} onAdd={openCreate} />
        ) : (
          <TrackerTable
            rows={rows}
            labels={labels}
            isArchive={isArchive}
            onEdit={openEdit}
          />
        )}
      </div>

      <JobDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        appId={editId}
      />
    </section>
  );
}

/** Client-side label fallback (the list view has no GET-one to source labels
 * from). Kept in sync with db.STATUS_LABELS; statusLabel() Title-Cases anything
 * missing so a new status still renders. */
const STATIC_LABELS: Record<string, string> = {
  interested: "Interested",
  applied: "Applied",
  phone_screen: "Phone Screen",
  interview: "Interview",
  offer: "Offer",
  accepted: "Accepted",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
  ghosted: "Ghosted",
};

function Header({
  followupsDue,
  onAdd,
  total,
}: {
  followupsDue: number;
  onAdd: () => void;
  total: number;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="space-y-1">
        <h1
          id="tracker-heading"
          className="zg-serif text-foreground flex items-center gap-2.5 text-2xl font-semibold tracking-tight"
        >
          <ListChecks className="text-primary size-6" strokeWidth={2} />
          Tracker
        </h1>
        <p className="text-muted-foreground max-w-xl text-sm leading-relaxed">
          Every application in one place.{" "}
          {followupsDue > 0 ? (
            <span className="text-[var(--zg-warn)]">
              <Bell className="mb-0.5 mr-0.5 inline size-3.5" />
              {followupsDue} follow-up{followupsDue === 1 ? "" : "s"} due.
            </span>
          ) : (
            "Sort, filter, and advance the funnel."
          )}
        </p>
      </div>
      <div className="flex items-center gap-2">
        {total > 0 && (
          <span className="text-muted-foreground zg-num hidden text-xs sm:inline">
            {total} tracked
          </span>
        )}
        <Button onClick={onAdd}>
          <Plus className="size-4" />
          Add job
        </Button>
      </div>
    </div>
  );
}

// ── Filter chip-bar ───────────────────────────────────────────────────────────

const FILTER_ORDER = [
  "interested",
  "applied",
  "phone_screen",
  "interview",
  "offer",
  "accepted",
  "rejected",
  "withdrawn",
  "ghosted",
] as const;

function FilterBar({
  view,
  onView,
  counts,
  labels,
}: {
  view: string;
  onView: (v: string) => void;
  counts: Record<string, number>;
  labels: Record<string, string>;
}) {
  return (
    <div
      role="tablist"
      aria-label="Filter applications by status"
      className="scrollbar-none mt-5 flex items-center gap-1.5 overflow-x-auto pb-1"
    >
      <FilterChip
        label="All"
        count={counts.all ?? 0}
        active={view === "all"}
        onClick={() => onView("all")}
      />
      {FILTER_ORDER.map((s) => (
        <FilterChip
          key={s}
          label={statusLabel(s, labels)}
          count={counts[s] ?? 0}
          active={view === s}
          status={s}
          onClick={() => onView(s)}
        />
      ))}
      <span className="mx-1 h-5 w-px shrink-0 bg-border" aria-hidden />
      <FilterChip
        label="Archive"
        count={counts.archived ?? 0}
        active={view === "archived"}
        icon={<Archive className="size-3.5" />}
        onClick={() => onView("archived")}
      />
    </div>
  );
}

function FilterChip({
  label,
  count,
  active,
  status,
  icon,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  status?: string;
  icon?: React.ReactNode;
  onClick: () => void;
}) {
  // Active chip is filled with the status color (or accent for All/Archive);
  // idle chips are hairline. The count is a mono numeral.
  const color = status
    ? `var(--zg-status-${status.replace(/_/g, "-")})`
    : undefined;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-[var(--radius-chip)] border px-2.5 py-1 text-xs font-medium transition-colors",
        "focus-visible:ring-ring/50 outline-none focus-visible:ring-2",
        active
          ? undefined
          : "border-border text-muted-foreground hover:text-foreground hover:border-ring/40",
      )}
      style={
        active
          ? color
            ? {
                backgroundColor: color,
                borderColor: color,
                color: "var(--zg-accent-fg)",
              }
            : {
                backgroundColor: "var(--zg-accent)",
                borderColor: "var(--zg-accent)",
                color: "var(--zg-accent-fg)",
              }
          : color
            ? statusChipBorderTint(color)
            : undefined
      }
    >
      {icon}
      {label}
      <span
        className={cn(
          "zg-num rounded px-1 text-[0.7rem]",
          active ? "" : "bg-secondary text-muted-foreground",
        )}
        style={
          active
            ? {
                backgroundColor:
                  "color-mix(in oklab, var(--zg-accent-fg) 20%, transparent)",
              }
            : undefined
        }
      >
        {count}
      </span>
    </button>
  );
}

// ── The table ─────────────────────────────────────────────────────────────────

function TrackerTable({
  rows,
  labels,
  isArchive,
  onEdit,
}: {
  rows: AppRow[];
  labels: Record<string, string>;
  isArchive: boolean;
  onEdit: (id: number) => void;
}) {
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const today = React.useMemo(() => todayIso(), []);

  const setStatus = useSetApplicationStatus();
  const archive = useArchiveApplication();
  const restore = useRestoreApplication();
  const del = useDeleteApplication();
  const [confirmDelete, setConfirmDelete] = React.useState<AppRow | null>(null);

  const onQuickStatus = (row: AppRow, status: string) => {
    if (status === row.status) return;
    setStatus.mutate(
      { id: row.id, status },
      {
        onSuccess: () =>
          toast.success("Status updated", {
            description: `${row.title} → ${statusLabel(status, labels)}.`,
          }),
        onError: (e) =>
          toast.error("Couldn't update status", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          }),
      },
    );
  };

  const columns = React.useMemo(
    () => [
      columnHelper.accessor("title", {
        header: "Role",
        cell: (ctx) => {
          const row = ctx.row.original;
          const due = isFollowupDue(row, today);
          return (
            <div className="flex items-start gap-2">
              {due && (
                <span
                  title="Follow-up due"
                  aria-label="Follow-up due"
                  className="mt-1.5 size-2 shrink-0 rounded-full bg-[var(--zg-warn)]"
                />
              )}
              <div className="flex min-w-0 flex-col gap-0.5">
                <button
                  type="button"
                  onClick={() => onEdit(row.id)}
                  className="text-foreground hover:text-primary text-left leading-snug font-medium transition-colors"
                >
                  {row.title || "Untitled role"}
                </button>
                <span className="text-muted-foreground truncate text-xs">
                  {row.location || "—"}
                </span>
              </div>
            </div>
          );
        },
      }),
      columnHelper.accessor("company", {
        header: "Company",
        cell: (ctx) => (
          <span className="text-foreground text-sm">
            {ctx.getValue() || "—"}
          </span>
        ),
      }),
      columnHelper.accessor("status", {
        header: "Status",
        cell: (ctx) => {
          const row = ctx.row.original;
          if (isArchive) {
            return <StatusChip status={row.status} labels={labels} />;
          }
          return (
            <QuickStatus
              row={row}
              labels={labels}
              onChange={(s) => onQuickStatus(row, s)}
            />
          );
        },
      }),
      columnHelper.accessor("date_applied", {
        header: "Applied",
        cell: (ctx) => (
          <span className="zg-num text-muted-foreground text-xs">
            {(ctx.getValue() as string) || "—"}
          </span>
        ),
        sortUndefined: "last",
      }),
      columnHelper.accessor((r) => r.follow_up_date ?? "", {
        id: "follow_up",
        header: "Follow-up",
        cell: (ctx) => {
          const row = ctx.row.original;
          const f = (row.follow_up_date ?? "").trim();
          if (!f) return <span className="text-muted-foreground/50">—</span>;
          const due = isFollowupDue(row, today);
          return (
            <div className="flex flex-col gap-0.5">
              <span
                className={cn(
                  "zg-num text-xs",
                  due
                    ? "font-medium text-[var(--zg-warn)]"
                    : "text-muted-foreground",
                )}
              >
                {f}
              </span>
              {due && (
                <button
                  type="button"
                  onClick={() => onEdit(row.id)}
                  className="text-primary hover:underline text-left text-xs"
                  title="Open this application and draft a follow-up"
                >
                  Draft it
                </button>
              )}
            </div>
          );
        },
      }),
      columnHelper.display({
        id: "actions",
        header: () => <span className="sr-only">Actions</span>,
        cell: (ctx) => {
          const row = ctx.row.original;
          return (
            <RowActions
              row={row}
              isArchive={isArchive}
              onEdit={() => onEdit(row.id)}
              onArchive={() =>
                archive.mutate(row.id, {
                  onSuccess: () =>
                    toast("Archived", {
                      description: `${row.title} moved to the archive.`,
                    }),
                  onError: (e) =>
                    toast.error("Couldn't archive", {
                      description:
                        e instanceof ApiError ? e.message : "Please try again.",
                    }),
                })
              }
              onRestore={() =>
                restore.mutate(row.id, {
                  onSuccess: () =>
                    toast.success("Restored", {
                      description: `${row.title} is active again.`,
                    }),
                })
              }
              onDelete={() => setConfirmDelete(row)}
            />
          );
        },
      }),
    ],
    [labels, isArchive, today, onEdit, archive, restore],
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: (r) => String(r.id),
  });

  return (
    <>
      <div className="overflow-x-auto rounded-lg border border-border bg-card">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id} className="hover:bg-transparent">
                {hg.headers.map((h) => {
                  const sortable = h.column.getCanSort();
                  const sorted = h.column.getIsSorted();
                  return (
                    <TableHead
                      key={h.id}
                      className={cn(
                        h.column.id === "actions" && "w-[7rem] text-right",
                      )}
                    >
                      {sortable ? (
                        <button
                          type="button"
                          onClick={h.column.getToggleSortingHandler()}
                          className="hover:text-foreground inline-flex items-center gap-1 transition-colors"
                        >
                          {flexRender(
                            h.column.columnDef.header,
                            h.getContext(),
                          )}
                          <SortIcon dir={sorted} />
                        </button>
                      ) : (
                        flexRender(h.column.columnDef.header, h.getContext())
                      )}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((tr) => (
              <TableRow key={tr.id} className="group">
                {tr.getVisibleCells().map((cell) => (
                  <TableCell
                    key={cell.id}
                    className={cn(cell.column.id === "actions" && "text-right")}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <ConfirmDialog
        open={confirmDelete !== null}
        onOpenChange={(o) => !o && setConfirmDelete(null)}
        title="Delete permanently?"
        description={
          confirmDelete
            ? `“${confirmDelete.title} · ${confirmDelete.company}” will be removed for good. This can't be undone.`
            : ""
        }
        confirmLabel="Delete"
        cancelLabel="Keep"
        destructive
        onConfirm={() => {
          if (!confirmDelete) return;
          const row = confirmDelete;
          del.mutate(row.id, {
            onSuccess: () =>
              toast("Deleted", { description: `${row.title} removed.` }),
            onError: (e) =>
              toast.error("Couldn't delete", {
                description:
                  e instanceof ApiError ? e.message : "Please try again.",
              }),
          });
        }}
      />
    </>
  );
}

function SortIcon({ dir }: { dir: false | "asc" | "desc" }) {
  if (dir === "asc") return <ArrowUp className="size-3" />;
  if (dir === "desc") return <ArrowDown className="size-3" />;
  return <ArrowUpDown className="size-3 opacity-40" />;
}

/** Inline quick-status select — an unstyled native select wearing the status chip
 * so the whole chip is the control. Changing it fires the funnel move. */
function QuickStatus({
  row,
  labels,
  onChange,
}: {
  row: AppRow;
  labels: Record<string, string>;
  onChange: (status: string) => void;
}) {
  const color = `var(--zg-status-${(row.status || "").replace(/_/g, "-")})`;
  return (
    <div className="relative inline-flex">
      <span
        className="inline-flex items-center gap-1.5 rounded-[var(--radius-chip)] border px-2 py-0.5 text-xs font-medium"
        style={statusChipStyle(color)}
      >
        <span
          aria-hidden
          className="size-1.5 rounded-full"
          style={{ backgroundColor: color }}
        />
        {statusLabel(row.status, labels)}
      </span>
      <select
        aria-label={`Change status for ${row.title}`}
        value={row.status}
        onChange={(e) => onChange(e.target.value)}
        className="absolute inset-0 cursor-pointer opacity-0"
      >
        {FILTER_ORDER.map((s) => (
          <option key={s} value={s}>
            {statusLabel(s, labels)}
          </option>
        ))}
      </select>
    </div>
  );
}

function RowActions({
  row,
  isArchive,
  onEdit,
  onArchive,
  onRestore,
  onDelete,
}: {
  row: AppRow;
  isArchive: boolean;
  onEdit: () => void;
  onArchive: () => void;
  onRestore: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="flex items-center justify-end gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 focus-within:opacity-100">
      {isArchive ? (
        <>
          <ActionBtn
            label="Restore"
            onClick={onRestore}
            icon={<ArchiveRestore className="size-4" />}
          />
          <ActionBtn
            label="Delete permanently"
            tone="danger"
            onClick={onDelete}
            icon={<Trash2 className="size-4" />}
          />
        </>
      ) : (
        <>
          <ActionBtn
            label="Edit"
            onClick={onEdit}
            icon={<Pencil className="size-4" />}
          />
          <ActionBtn
            label="Open URL"
            onClick={() =>
              row.url &&
              window.open(String(row.url), "_blank", "noopener,noreferrer")
            }
            disabled={!row.url}
            icon={<ExternalLink className="size-4" />}
          />
          <ActionBtn
            label="Archive"
            onClick={onArchive}
            icon={<Archive className="size-4" />}
          />
        </>
      )}
    </div>
  );
}

function ActionBtn({
  label,
  onClick,
  icon,
  tone = "muted",
  disabled,
}: {
  label: string;
  onClick: () => void;
  icon: React.ReactNode;
  tone?: "muted" | "danger";
  disabled?: boolean;
}) {
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className={cn(
        "text-muted-foreground size-8",
        tone === "danger" ? "hover:text-destructive" : "hover:text-primary",
      )}
    >
      {icon}
    </Button>
  );
}

function TrackerEmpty({ view, onAdd }: { view: string; onAdd: () => void }) {
  if (view === "archived") {
    return (
      <EmptyState
        icon={Archive}
        title="Nothing archived"
        message="Archived applications land here — hidden from your active list but never lost."
      />
    );
  }
  if (view !== "all") {
    return (
      <EmptyState
        icon={ListChecks}
        title={`No ${statusLabel(view, STATIC_LABELS).toLowerCase()} applications`}
        message="Nothing here yet. Switch to All to see everything, or advance a job into this stage."
      />
    );
  }
  return (
    <EmptyState
      icon={ListChecks}
      title="No applications yet"
      message="Track roles you're pursuing from anywhere — track a Top Pick, or add one manually to start your funnel."
      action={{ label: "Add your first job", onClick: onAdd }}
    />
  );
}
