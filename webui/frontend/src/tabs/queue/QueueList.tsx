import * as React from "react";
import {
  CheckCircle2,
  XCircle,
  ExternalLink,
  FileCheck2,
  Users,
} from "lucide-react";

import type { QueueRow } from "@/api/client";
import { ScoreChip } from "@/components/score-chip";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/* The ranked apply-queue list — a roving-focus list of cards, one per interested
 * job, in fit-else-score order (server-provided; queue-order.ts proves the parity).
 * Each card: rank, fit-else-score chip, role/company, an ATS chip + referral line
 * when present, a docs-ready check. Selecting a card fills the detail rail; t/d/o on
 * the focused card mark-applied / dismiss / open (auto-advance handled by the tab).
 * The row buttons are the pointer path. */

export interface QueueListProps {
  rows: QueueRow[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onMarkApplied: (row: QueueRow) => void;
  onDismiss: (row: QueueRow) => void;
  onOpen: (row: QueueRow) => void;
}

/** The AI fit leads; fall back to the base score (parity with the queue ordering). */
function fitValue(row: QueueRow): number | null | undefined {
  const f = row.fit_score;
  if (typeof f === "number" && f >= 0) return f;
  return row.score;
}

export function QueueList({
  rows,
  selectedId,
  onSelect,
  onMarkApplied,
  onDismiss,
  onOpen,
}: QueueListProps) {
  const [focused, setFocused] = React.useState(0);
  const rowRefs = React.useRef<(HTMLDivElement | null)[]>([]);

  React.useEffect(() => {
    if (focused > rows.length - 1) setFocused(Math.max(0, rows.length - 1));
  }, [rows.length, focused]);

  const focusRow = (i: number) => {
    const clamped = Math.max(0, Math.min(rows.length - 1, i));
    setFocused(clamped);
    rowRefs.current[clamped]?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent, row: QueueRow, i: number) => {
    switch (e.key.toLowerCase()) {
      case "t":
        e.preventDefault();
        onMarkApplied(row);
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

  return (
    <div
      className="border-border bg-card divide-border/60 divide-y overflow-hidden rounded-lg border"
      role="list"
    >
      {rows.map((row, i) => {
        const isSelected = row.id === selectedId;
        const hasDocs = Boolean(row.docs_path);
        return (
          <div
            key={row.id}
            role="listitem"
            ref={(el) => {
              rowRefs.current[i] = el;
            }}
            tabIndex={i === focused ? 0 : -1}
            onFocus={() => setFocused(i)}
            onKeyDown={(e) => onKeyDown(e, row, i)}
            onClick={() => onSelect(row.id)}
            aria-selected={isSelected}
            aria-label={`Rank ${i + 1}: ${row.title} at ${row.company}`}
            className={cn(
              "group hover:bg-secondary/45 flex cursor-pointer items-start gap-3 px-3 py-3 outline-none transition-colors",
              "focus-visible:bg-secondary/50 focus-visible:ring-ring/40 focus-visible:ring-2 focus-visible:ring-inset",
              isSelected && "bg-accent/60 hover:bg-accent/60",
            )}
          >
            <span className="zg-num text-muted-foreground w-6 shrink-0 pt-0.5 text-center text-sm font-semibold tabular-nums">
              {i + 1}
            </span>
            <div className="shrink-0 pt-0.5">
              <ScoreChip value={fitValue(row)} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-foreground truncate leading-snug font-medium">
                  {row.title || "Untitled role"}
                </span>
                {hasDocs && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <FileCheck2 className="size-3.5 shrink-0 text-[var(--zg-success)]" />
                    </TooltipTrigger>
                    <TooltipContent>Documents ready</TooltipContent>
                  </Tooltip>
                )}
              </div>
              <div className="text-muted-foreground mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                <span className="truncate">{row.company || "Unknown"}</span>
                {row.location && (
                  <>
                    <span aria-hidden>·</span>
                    <span className="truncate">{row.location}</span>
                  </>
                )}
                {row.ats_label && (
                  <span className="border-border rounded-[var(--radius-chip)] border px-1 py-0.5 text-[0.65rem] font-medium">
                    {row.ats_label}
                  </span>
                )}
              </div>
              {row.referral && (
                <p className="text-primary/90 mt-1 flex items-center gap-1 text-xs">
                  <Users className="size-3" />
                  <span className="truncate">{row.referral}</span>
                </p>
              )}
            </div>
            <div
              className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100 focus-within:opacity-100"
              onClick={(e) => e.stopPropagation()}
            >
              <IconAction
                label="Mark applied (t)"
                onClick={() => onMarkApplied(row)}
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
          </div>
        );
      })}
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
