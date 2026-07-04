import * as React from "react";
import { toast } from "sonner";
import { ClipboardList, Sparkles, ChevronDown, Layers } from "lucide-react";

import {
  useQueue,
  useInvalidateQueueViews,
  useSetApplicationStatus,
  useArchiveApplication,
} from "@/api/queries";
import { ApiError, endpoints, type QueueRow } from "@/api/client";
import { useRegisterCommands, type AppCommand } from "@/lib/app-commands";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import { PromptDialog } from "@/components/prompt-dialog";
import { PasteDialog } from "@/components/paste-dialog";

import { QueueList } from "./QueueList";
import { QueueDetail } from "./QueueDetail";
import { BatchDialog } from "./BatchDialog";

/* Apply Queue — every "interested" job ranked best-first, with the full
 * throughput toolkit: copy a tailoring prompt, paste a claude.ai reply → DOCX,
 * generate via API (when a key is set), mark applied → auto-advance, dismiss →
 * archive, a batch-of-5 round-trip, and an AI fit-ranking prompt/reply pair.
 *
 * Layout mirrors the Inbox: a ranked list (left) + a detail rail (right, the
 * selected job's fit rationale / ATS hint / referral + all its action buttons).
 * Ordering is server-provided (fit-else-score desc — queue-order.ts proves the
 * parity). Mark-applied advances selection to the next row so the funnel flows. */

export function ApplyQueueTab() {
  const query = useQueue();
  const invalidateQueue = useInvalidateQueueViews();
  const rows = React.useMemo(() => query.data?.rows ?? [], [query.data]);

  const [selectedId, setSelectedId] = React.useState<number | null>(null);
  const selectedRow = React.useMemo(
    () => rows.find((r) => r.id === selectedId) ?? null,
    [rows, selectedId],
  );

  // Default-select the first row when the list (re)loads with none selected.
  React.useEffect(() => {
    if (selectedId === null && rows.length > 0) setSelectedId(rows[0].id);
    if (selectedId !== null && !rows.some((r) => r.id === selectedId)) {
      setSelectedId(rows[0]?.id ?? null);
    }
  }, [rows, selectedId]);

  const setStatus = useSetApplicationStatus();
  const archive = useArchiveApplication();

  // ── mark applied → advance to next ──────────────────────────────────────────
  const advanceFrom = React.useCallback(
    (id: number) => {
      const idx = rows.findIndex((r) => r.id === id);
      // The current row leaves the queue (applied/archived), so "next" is the row
      // that will slide into its index (or the previous one if it was last).
      const next = rows[idx + 1] ?? rows[idx - 1] ?? null;
      setSelectedId(next ? next.id : null);
    },
    [rows],
  );

  const onMarkApplied = React.useCallback(
    (row: QueueRow) => {
      advanceFrom(row.id);
      setStatus.mutate(
        { id: row.id, status: "applied" },
        {
          onSuccess: () =>
            toast.success("Applied", {
              description: `${row.title} @ ${row.company} — on to the next.`,
            }),
          onError: (e) =>
            toast.error("Couldn't mark applied", {
              description:
                e instanceof ApiError ? e.message : "Please try again.",
            }),
        },
      );
    },
    [advanceFrom, setStatus],
  );

  const [confirmDismiss, setConfirmDismiss] = React.useState<QueueRow | null>(
    null,
  );
  const onDismiss = React.useCallback(
    (row: QueueRow) => {
      advanceFrom(row.id);
      archive.mutate(row.id, {
        onSuccess: () =>
          toast("Dismissed", {
            description: `${row.title} @ ${row.company} archived — restore it from the Tracker archive.`,
          }),
        onError: (e) =>
          toast.error("Couldn't dismiss", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          }),
      });
    },
    [advanceFrom, archive],
  );

  const onOpen = React.useCallback((row: QueueRow) => {
    if (row.url) window.open(String(row.url), "_blank", "noopener,noreferrer");
  }, []);

  // ── batch + rank dialogs ────────────────────────────────────────────────────
  const [batchOpen, setBatchOpen] = React.useState(false);
  const [rankPrompt, setRankPrompt] = React.useState<{
    prompt: string;
    dropped: number;
  } | null>(null);
  const [rankReplyOpen, setRankReplyOpen] = React.useState(false);
  const [rankPending, setRankPending] = React.useState(false);

  const openRankPrompt = React.useCallback(() => {
    endpoints
      .queueRankPrompt()
      .then((r) => {
        if (!r.prompt) {
          const reasons = Array.from(
            new Set(r.dropped.flatMap((d) => d.reasons)),
          ).join(", ");
          toast("Nothing to rank", {
            description: r.dropped.length
              ? `Every queued job was auto-filtered (${reasons || "structural non-fit"}).`
              : "Your apply queue is empty.",
          });
          return;
        }
        setRankPrompt({ prompt: r.prompt, dropped: r.dropped.length });
      })
      .catch((e) =>
        toast.error("Couldn't build the ranking prompt", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
      );
  }, []);

  const submitRankReply = React.useCallback(
    (text: string) => {
      setRankPending(true);
      endpoints
        .queueRankReply(text)
        .then((r) => {
          toast.success("Fit scores applied", {
            description: `${r.applied} job${r.applied === 1 ? "" : "s"} re-ranked.`,
          });
          setRankReplyOpen(false);
          invalidateQueue();
        })
        .catch((e) =>
          toast.error("Couldn't apply the ranking", {
            description:
              e instanceof ApiError ? e.message : "Check the reply and retry.",
          }),
        )
        .finally(() => setRankPending(false));
    },
    [invalidateQueue],
  );

  // ── palette commands ────────────────────────────────────────────────────────
  const paletteCommands = React.useMemo<AppCommand[]>(
    () => [
      {
        id: "batch-prompt",
        label: "Batch resume prompt (top 5)",
        icon: Layers,
        run: () => setBatchOpen(true),
      },
      {
        id: "ask-ai-rank",
        label: "Ask AI to rank the apply queue",
        icon: Sparkles,
        run: openRankPrompt,
      },
    ],
    [openRankPrompt],
  );
  useRegisterCommands("apply-queue", paletteCommands);

  return (
    <section aria-labelledby="queue-heading" className="flex h-full flex-col">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1
            id="queue-heading"
            className="zg-serif text-foreground flex items-center gap-2.5 text-2xl font-semibold tracking-tight"
          >
            <ClipboardList className="text-primary size-6" strokeWidth={2} />
            Apply Queue
          </h1>
          <p className="text-muted-foreground max-w-xl text-sm leading-relaxed">
            Jobs you're interested in, best match first. Make tailored docs,
            then <Kbd>t</Kbd> mark applied, <Kbd>d</Kbd> dismiss, <Kbd>o</Kbd>{" "}
            open.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <RankMenu
            onPrompt={openRankPrompt}
            onPasteReply={() => setRankReplyOpen(true)}
          />
          <Button
            variant="outline"
            onClick={() => setBatchOpen(true)}
            disabled={rows.length === 0}
          >
            <Layers className="size-4" />
            Batch prompt (top 5)
          </Button>
        </div>
      </div>

      {/* Split body */}
      <div className="mt-5 flex min-h-0 flex-1 gap-4">
        <div className="min-w-0 flex-1 lg:max-w-[calc(100%-26rem)]">
          {query.isLoading ? (
            <div className="border-border bg-card rounded-lg border p-2">
              <TableSkeleton rows={8} />
            </div>
          ) : query.isError ? (
            <ErrorState
              title="Couldn't load your apply queue"
              message={
                query.error instanceof ApiError
                  ? query.error.message
                  : "The queue service didn't respond."
              }
              onRetry={() => query.refetch()}
            />
          ) : rows.length === 0 ? (
            <QueueEmpty />
          ) : (
            <QueueList
              rows={rows}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onMarkApplied={onMarkApplied}
              onDismiss={(r) => setConfirmDismiss(r)}
              onOpen={onOpen}
            />
          )}
        </div>

        {rows.length > 0 && (
          <aside className="border-border bg-card hidden w-[25rem] shrink-0 rounded-lg border lg:block">
            <QueueDetail
              row={selectedRow}
              onMarkApplied={onMarkApplied}
              onDismiss={(r) => setConfirmDismiss(r)}
              onOpen={onOpen}
              onDocsSaved={invalidateQueue}
            />
          </aside>
        )}
      </div>

      {/* Batch round-trip */}
      <BatchDialog
        open={batchOpen}
        onOpenChange={setBatchOpen}
        rows={rows}
        onDone={invalidateQueue}
      />

      {/* Fit-rank prompt */}
      <PromptDialog
        open={rankPrompt !== null}
        onOpenChange={(o) => !o && setRankPrompt(null)}
        title="Ask AI to rank these jobs"
        description="Paste this into claude.ai (or any AI), then paste the reply back with “Paste AI ranking” to apply the fit scores."
        prompt={rankPrompt?.prompt ?? ""}
      >
        {rankPrompt && rankPrompt.dropped > 0 && (
          <p className="text-muted-foreground -mt-1 text-xs">
            {rankPrompt.dropped} job{rankPrompt.dropped === 1 ? "" : "s"}{" "}
            auto-filtered as a structural non-fit before ranking.
          </p>
        )}
      </PromptDialog>

      {/* Fit-rank reply */}
      <PasteDialog
        open={rankReplyOpen}
        onOpenChange={setRankReplyOpen}
        title="Paste the AI ranking"
        description="Paste the AI's reply to the ranking prompt. Fit scores are applied to the matching queued jobs."
        placeholder="Paste the AI's ranking reply here…"
        submitLabel="Apply scores"
        pending={rankPending}
        onSubmit={submitRankReply}
      />

      <ConfirmDialog
        open={confirmDismiss !== null}
        onOpenChange={(o) => !o && setConfirmDismiss(null)}
        title="Dismiss this job?"
        description={
          confirmDismiss
            ? `“${confirmDismiss.title} · ${confirmDismiss.company}” will be archived and leave the queue. You can restore it from the Tracker archive.`
            : ""
        }
        confirmLabel="Dismiss"
        cancelLabel="Keep"
        onConfirm={() => confirmDismiss && onDismiss(confirmDismiss)}
      />
    </section>
  );
}

function RankMenu({
  onPrompt,
  onPasteReply,
}: {
  onPrompt: () => void;
  onPasteReply: () => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" className="gap-1.5">
          <Sparkles className="text-primary size-4" />
          Ask AI to rank
          <ChevronDown className="size-3.5 opacity-70" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>Bring your own AI</DropdownMenuLabel>
        <DropdownMenuItem onSelect={onPrompt}>
          <Sparkles className="size-4" />
          Copy ranking prompt…
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={onPasteReply}>
          <ClipboardList className="size-4" />
          Paste AI ranking…
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function QueueEmpty() {
  return (
    <EmptyState
      icon={ClipboardList}
      title="Nothing to apply to yet"
      message="Your apply queue is every job you've marked interested. Track a Top Pick or an Inbox match, and it lands here — ranked, ready to tailor and apply."
    />
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="border-border bg-secondary text-foreground zg-num mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded border px-1 text-[0.7rem]">
      {children}
    </kbd>
  );
}
