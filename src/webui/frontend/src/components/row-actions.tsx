import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/* The hover/focus-reveal row-action cluster shared by every triage table/list:
 * Inbox, Top Picks, Search results, and the Apply Queue list. Each row's actions
 * differ (Queue's are mark-applied/dismiss/open, not track/dismiss/open) but the
 * per-icon tone-color + tooltip treatment and the reveal wrapper are identical
 * across all four — this is that shared pair, pulled out of the four near-
 * identical local copies. Pure refactor: no behavior change. */

export type IconActionTone = "success" | "danger" | "muted";

const TONE_CLASS: Record<IconActionTone, string> = {
  success: "hover:text-[var(--zg-success)]",
  danger: "hover:text-destructive",
  muted: "hover:text-primary",
};

/** One ghost icon-button with a tone-based hover color and a tooltip label —
 * the ubiquitous per-row action button (Track / Dismiss / Open / Mark applied).
 * `tabIndex={-1}` keeps it out of the row's own tab order; the roving-focus row
 * + t/d/o keys are the primary keyboard path, this is the pointer path. */
export function IconAction({
  label,
  onClick,
  icon,
  tone,
  disabled,
}: {
  label: string;
  onClick: () => void;
  icon: React.ReactNode;
  tone: IconActionTone;
  disabled?: boolean;
}) {
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
          className={cn("text-muted-foreground size-8", TONE_CLASS[tone])}
        >
          {icon}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

/** One row's worth of IconAction props — what each tab supplies per action. */
export interface TriageAction {
  key: string;
  label: string;
  onClick: () => void;
  icon: React.ReactNode;
  tone: IconActionTone;
  disabled?: boolean;
}

/** The reveal wrapper + IconAction cluster for a table row / list card:
 * invisible at rest, opacity-100 on row hover/focus-within (keyboard-reachable
 * even though it's visually hidden until then). `justify` controls the flex
 * justification (table cells right-align; the Queue list card's actions sit at
 * the end of an already-justified row, so it doesn't need justify-end). */
export function TriageActions({
  actions,
  justify = true,
  stopPropagation = true,
  className,
}: {
  actions: TriageAction[];
  /** Add `justify-end` to the wrapper (table-cell layouts). Default true. */
  justify?: boolean;
  /** Stop click propagation so a row-click select doesn't also fire (table
   * rows are clickable; default true). */
  stopPropagation?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 focus-within:opacity-100",
        justify && "justify-end",
        className,
      )}
      onClick={stopPropagation ? (e) => e.stopPropagation() : undefined}
    >
      {actions.map((a) => (
        <IconAction
          key={a.key}
          label={a.label}
          onClick={a.onClick}
          icon={a.icon}
          tone={a.tone}
          disabled={a.disabled}
        />
      ))}
    </div>
  );
}
