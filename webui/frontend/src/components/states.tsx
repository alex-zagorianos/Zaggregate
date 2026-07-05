import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Inbox, AlertTriangle, Loader2, MousePointerClick } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

/* Shared full-panel states — the web twins of ui.theme.empty_state. Every tab
 * uses these so "nothing here", "it broke", and "loading" read identically
 * across the app. Centered, generous whitespace, faint icon, one optional CTA. */

interface EmptyStateProps {
  icon?: LucideIcon;
  /** Extra classes for the icon glyph (e.g. "animate-spin" for Loader2). */
  iconClassName?: string;
  title: string;
  message?: string;
  action?: { label: string; onClick: () => void };
  /** Optional custom content below the message (e.g. an illustrative flow).
   * Rendered after `action` if both are given. */
  children?: ReactNode;
  className?: string;
}

export function EmptyState({
  icon: Icon = Inbox,
  iconClassName,
  title,
  message,
  action,
  children,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex min-h-[46vh] flex-col items-center justify-center px-6 text-center",
        className,
      )}
    >
      <div className="text-muted-foreground/40 mb-5">
        <Icon className={cn("size-12", iconClassName)} strokeWidth={1.25} />
      </div>
      <h3 className="zg-serif text-foreground text-xl font-medium tracking-tight">
        {title}
      </h3>
      {message && (
        <p className="text-muted-foreground mt-2 max-w-md text-sm leading-relaxed">
          {message}
        </p>
      )}
      {action && (
        <Button className="mt-6" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
      {children}
    </div>
  );
}

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        "flex min-h-[46vh] flex-col items-center justify-center px-6 text-center",
        className,
      )}
    >
      <div className="text-destructive/70 mb-5">
        <AlertTriangle className="size-11" strokeWidth={1.25} />
      </div>
      <h3 className="zg-serif text-foreground text-xl font-medium tracking-tight">
        {title}
      </h3>
      {message && (
        <p className="text-muted-foreground mt-2 max-w-md text-sm leading-relaxed break-words">
          {message}
        </p>
      )}
      {onRetry && (
        <Button variant="outline" className="mt-6" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function LoadingState({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex min-h-[46vh] flex-col items-center justify-center gap-3",
        className,
      )}
    >
      <Loader2 className="text-muted-foreground/60 size-7 animate-spin" />
      <span className="text-muted-foreground text-sm">Loading…</span>
    </div>
  );
}

interface SelectPromptProps {
  icon?: LucideIcon;
  title: string;
  message: string;
}

/** The "nothing selected yet" placeholder for a split-view detail rail — the
 * Inbox and Apply Queue detail panes both show this before a row is picked.
 * Smaller and quieter than EmptyState (no CTA, tighter icon), since it's a
 * transient prompt inside an already-populated layout, not a whole-panel empty
 * state. */
export function SelectPrompt({
  icon: Icon = MousePointerClick,
  title,
  message,
}: SelectPromptProps) {
  return (
    <div className="flex min-h-[46vh] flex-col items-center justify-center px-6 text-center">
      <Icon
        className="text-muted-foreground/40 mb-4 size-10"
        strokeWidth={1.25}
      />
      <p className="zg-serif text-foreground text-lg font-medium">{title}</p>
      <p className="text-muted-foreground mt-1.5 max-w-xs text-sm leading-relaxed">
        {message}
      </p>
    </div>
  );
}

/** A table-shaped skeleton for list/table loading (Phase 1+ tables reuse this). */
export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-1">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4">
          <Skeleton className="h-6 w-10" />
          <Skeleton className="h-6 flex-1" />
          <Skeleton className="h-6 w-28" />
          <Skeleton className="h-6 w-16" />
        </div>
      ))}
    </div>
  );
}
