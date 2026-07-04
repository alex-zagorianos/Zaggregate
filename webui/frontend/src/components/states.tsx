import type { LucideIcon } from "lucide-react";
import { Inbox, AlertTriangle, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

/* Shared full-panel states — the web twins of ui.theme.empty_state. Every tab
 * uses these so "nothing here", "it broke", and "loading" read identically
 * across the app. Centered, generous whitespace, faint icon, one optional CTA. */

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  message?: string;
  action?: { label: string; onClick: () => void };
  className?: string;
}

export function EmptyState({
  icon: Icon = Inbox,
  title,
  message,
  action,
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
        <Icon className="size-12" strokeWidth={1.25} />
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
