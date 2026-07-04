import * as React from "react";
import { toast } from "sonner";
import {
  DndContext,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  useDraggable,
  useDroppable,
  DragOverlay,
  pointerWithin,
  type DragStartEvent,
  type DragEndEvent,
} from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import {
  KanbanSquare,
  ChevronRight,
  GripVertical,
  MoveRight,
} from "lucide-react";

import { useBoard, useMoveCard } from "@/api/queries";
import { ApiError, type BoardColumn, type BoardCardRow } from "@/api/client";
import { statusLabel, isTerminal } from "@/lib/status";
import { daysInStageLabel } from "@/lib/board-labels";
import { canDrop, isRealMove, rejectReason } from "./board-logic";
import { JobDialog } from "@/components/job-dialog";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

/* Board — the kanban funnel, the web twin of ui/kanban.py. One column per status
 * (label + count, header tinted with --zg-status-*); cards are draggable ONLY to
 * their server-computed forward_targets. On drag, the valid columns highlight and
 * the invalid ones dim; an invalid drop snaps back with a toast that explains the
 * rule. A valid drop is optimistic (card moves instantly, rolls back on error)
 * and posts the status. Every card also keeps a "Move ▸" dropdown listing its
 * forward_targets — the keyboard/a11y path that doesn't require pointer dragging.
 * Double-click / Enter on a card opens the JobDialog. The board scrolls
 * horizontally with edge fades (the tab-nav mask pattern); terminal columns read
 * calmer (muted headers). */

export function BoardTab() {
  const query = useBoard();
  const move = useMoveCard();
  const columns = query.data?.columns ?? [];

  // Which card is being dragged (for the overlay) + which columns are valid drop
  // targets for it (for the highlight). Cleared on drag end.
  const [activeCard, setActiveCard] = React.useState<BoardCardRow | null>(null);

  // JobDialog state.
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [editId, setEditId] = React.useState<number | null>(null);
  const openEdit = (id: number) => {
    setEditId(id);
    setDialogOpen(true);
  };

  const labelOf = React.useCallback(
    (s: string) => statusLabel(s, undefined),
    [],
  );

  const sensors = useSensors(
    // A small activation distance so a click-to-open isn't hijacked as a drag.
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor),
  );

  const onDragStart = (e: DragStartEvent) => {
    setActiveCard((e.active.data.current?.card as BoardCardRow) ?? null);
  };

  const onDragEnd = (e: DragEndEvent) => {
    const card = e.active.data.current?.card as BoardCardRow | undefined;
    setActiveCard(null);
    if (!card || !e.over) return;
    const target = String(e.over.id);
    if (!isRealMove(card, target)) {
      // A no-op self-drop is silent; a genuinely invalid target explains itself.
      if (!canDrop(card, target)) {
        toast.error("Can't drop there", {
          description: rejectReason(card, target, labelOf),
        });
      }
      return;
    }
    move.mutate(
      { id: card.id, status: target },
      {
        onSuccess: () =>
          toast.success("Moved", {
            description: `${card.company || card.title} → ${labelOf(target)}.`,
          }),
        onError: (err) =>
          toast.error("Couldn't move", {
            description:
              err instanceof ApiError ? err.message : "Change reverted.",
          }),
      },
    );
  };

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return (
      <ErrorState
        title="Couldn't load your board"
        message={
          query.error instanceof ApiError
            ? query.error.message
            : "The board service didn't respond."
        }
        onRetry={() => query.refetch()}
      />
    );
  }

  const totalCards = columns.reduce((n, c) => n + c.cards.length, 0);

  return (
    <section aria-labelledby="board-heading" className="flex h-full flex-col">
      <div className="mb-5 space-y-1">
        <h1
          id="board-heading"
          className="zg-serif text-foreground flex items-center gap-2.5 text-2xl font-semibold tracking-tight"
        >
          <KanbanSquare className="text-primary size-6" strokeWidth={2} />
          Board
        </h1>
        <p className="text-muted-foreground max-w-xl text-sm leading-relaxed">
          Drag a card forward through the funnel, or use its{" "}
          <span className="text-foreground">Move ▸</span> menu. Double-click a
          card to edit it.
        </p>
      </div>

      {totalCards === 0 ? (
        <BoardEmpty />
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={pointerWithin}
          onDragStart={onDragStart}
          onDragEnd={onDragEnd}
          onDragCancel={() => setActiveCard(null)}
        >
          <div className="relative min-h-0 flex-1">
            <div
              className="scrollbar-none flex h-full gap-4 overflow-x-auto pb-3"
              style={{
                maskImage:
                  "linear-gradient(to right, transparent 0, #000 24px, #000 calc(100% - 24px), transparent 100%)",
                WebkitMaskImage:
                  "linear-gradient(to right, transparent 0, #000 24px, #000 calc(100% - 24px), transparent 100%)",
              }}
            >
              {columns.map((col) => (
                <Column
                  key={col.status}
                  column={col}
                  activeCard={activeCard}
                  onEdit={openEdit}
                  onMove={(cardId, target, card) => {
                    if (!isRealMove(card, target)) return;
                    move.mutate(
                      { id: cardId, status: target },
                      {
                        onSuccess: () =>
                          toast.success("Moved", {
                            description: `${card.company || card.title} → ${labelOf(target)}.`,
                          }),
                        onError: (err) =>
                          toast.error("Couldn't move", {
                            description:
                              err instanceof ApiError
                                ? err.message
                                : "Change reverted.",
                          }),
                      },
                    );
                  }}
                />
              ))}
            </div>
          </div>

          <DragOverlay dropAnimation={null}>
            {activeCard ? (
              <CardBody card={activeCard} dragging labelOf={labelOf} />
            ) : null}
          </DragOverlay>
        </DndContext>
      )}

      <JobDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        appId={editId}
      />
    </section>
  );
}

// ── Column ────────────────────────────────────────────────────────────────────

function Column({
  column,
  activeCard,
  onEdit,
  onMove,
}: {
  column: BoardColumn;
  activeCard: BoardCardRow | null;
  onEdit: (id: number) => void;
  onMove: (cardId: number, target: string, card: BoardCardRow) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: column.status });
  const terminal = isTerminal(column.status);
  const color = `var(--zg-status-${column.status.replace(/_/g, "-")})`;

  // Highlight logic during a drag: a column is a valid target when the dragged
  // card lists it (or it's the card's own column). Invalid columns dim.
  const dragging = activeCard !== null;
  const valid =
    dragging && activeCard
      ? canDrop(activeCard, column.status) &&
        column.status !== (activeCard.status ?? "")
      : false;
  const invalid =
    dragging && !valid && activeCard
      ? column.status !== (activeCard.status ?? "")
      : false;

  return (
    <div
      className={cn(
        "flex w-72 shrink-0 flex-col rounded-lg border transition-all duration-150",
        valid && isOver
          ? "border-transparent ring-2"
          : valid
            ? "border-dashed"
            : "border-border",
        invalid && "opacity-45",
      )}
      style={{
        ...(valid
          ? {
              borderColor: `color-mix(in oklab, ${color} 50%, transparent)`,
              backgroundColor: `color-mix(in oklab, ${color} 6%, transparent)`,
              ...(isOver
                ? ({ "--tw-ring-color": color } as React.CSSProperties)
                : {}),
            }
          : {}),
      }}
    >
      {/* Header — tinted with the status token; terminal columns render calmer. */}
      <div
        className={cn(
          "flex items-center justify-between rounded-t-lg border-b border-border px-3 py-2.5",
        )}
        style={{
          backgroundColor: terminal
            ? "color-mix(in oklab, var(--zg-muted) 8%, transparent)"
            : `color-mix(in oklab, ${color} 12%, transparent)`,
        }}
      >
        <div className="flex items-center gap-2">
          <span
            aria-hidden
            className="size-2 rounded-full"
            style={{
              backgroundColor: terminal ? "var(--zg-faint)" : color,
            }}
          />
          <span
            className={cn(
              "text-sm font-semibold",
              terminal ? "text-muted-foreground" : "text-foreground",
            )}
          >
            {column.label}
          </span>
        </div>
        <span className="zg-num text-muted-foreground rounded bg-secondary px-1.5 text-xs">
          {column.cards.length}
        </span>
      </div>

      {/* Card stack — the droppable area. */}
      <div
        ref={setNodeRef}
        className="flex min-h-24 flex-1 flex-col gap-2 overflow-y-auto p-2"
      >
        {column.cards.length === 0 ? (
          <p className="text-muted-foreground/50 px-2 py-6 text-center text-xs">
            {valid ? "Drop here" : "—"}
          </p>
        ) : (
          column.cards.map((card) => (
            <DraggableCard
              key={card.id}
              card={card}
              onEdit={onEdit}
              onMove={onMove}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ── Card ──────────────────────────────────────────────────────────────────────

function DraggableCard({
  card,
  onEdit,
  onMove,
}: {
  card: BoardCardRow;
  onEdit: (id: number) => void;
  onMove: (cardId: number, target: string, card: BoardCardRow) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({ id: card.id, data: { card } });
  const labelOf = React.useCallback(
    (s: string) => statusLabel(s, undefined),
    [],
  );

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform) }}
      className={cn(isDragging && "opacity-40")}
    >
      <CardBody
        card={card}
        onEdit={onEdit}
        onMove={onMove}
        dragHandleProps={{ ...attributes, ...listeners }}
        labelOf={labelOf}
      />
    </div>
  );
}

function CardBody({
  card,
  onEdit,
  onMove,
  dragHandleProps,
  dragging,
  labelOf,
}: {
  card: BoardCardRow;
  onEdit?: (id: number) => void;
  onMove?: (cardId: number, target: string, card: BoardCardRow) => void;
  dragHandleProps?: React.HTMLAttributes<HTMLButtonElement>;
  dragging?: boolean;
  labelOf: (s: string) => string;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`${card.title} at ${card.company}. Enter to edit.`}
      onDoubleClick={() => onEdit?.(card.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          onEdit?.(card.id);
        }
      }}
      className={cn(
        "group/card bg-card focus-visible:ring-ring/50 rounded-md border border-border p-2.5 shadow-xs transition-shadow outline-none focus-visible:ring-2",
        dragging ? "cursor-grabbing shadow-lg" : "hover:shadow-md",
      )}
    >
      <div className="flex items-start gap-1.5">
        {dragHandleProps && (
          <button
            type="button"
            aria-label="Drag to move"
            className="text-muted-foreground/40 hover:text-muted-foreground -ml-1 mt-0.5 cursor-grab touch-none rounded p-0.5 transition-colors"
            {...dragHandleProps}
          >
            <GripVertical className="size-4" />
          </button>
        )}
        <div className="min-w-0 flex-1">
          <p className="text-foreground truncate text-sm font-semibold leading-snug">
            {card.company || "Unknown company"}
          </p>
          <p className="text-muted-foreground truncate text-xs leading-snug">
            {card.title || "Untitled role"}
          </p>
          {card.days_label && (
            <p className="text-muted-foreground/70 zg-num mt-1.5 text-[0.7rem]">
              {daysInStageLabel(card.days_label)}
            </p>
          )}
        </div>
        {onMove && card.forward_targets.length > 0 && (
          <MoveMenu card={card} onMove={onMove} labelOf={labelOf} />
        )}
      </div>
    </div>
  );
}

/** The keyboard/a11y move path: a dropdown listing the card's forward_targets.
 * Every drag-drop move is reproducible here without a pointer. */
function MoveMenu({
  card,
  onMove,
  labelOf,
}: {
  card: BoardCardRow;
  onMove: (cardId: number, target: string, card: BoardCardRow) => void;
  labelOf: (s: string) => string;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Move ${card.company}`}
          className="text-muted-foreground hover:text-primary size-7 shrink-0 opacity-0 transition-opacity group-hover/card:opacity-100 group-focus-within/card:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100"
        >
          <MoveRight className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>Move to</DropdownMenuLabel>
        {card.forward_targets.map((t) => (
          <DropdownMenuItem
            key={t}
            onSelect={() => onMove(card.id, t, card)}
            className="gap-2"
          >
            <ChevronRight className="size-3.5" />
            {labelOf(t)}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function BoardEmpty() {
  return (
    <EmptyState
      icon={KanbanSquare}
      title="Your board is empty"
      message="Track an application and it appears here as a card you can drag through the funnel — Interested → Applied → Interview → Offer."
    />
  );
}
