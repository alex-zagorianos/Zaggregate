import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Inbox, AlertTriangle, Loader2, MousePointerClick } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/api/client";

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

// ── useQueryGuard ─────────────────────────────────────────────────────────────

/** The minimal shape of a TanStack Query result this guard needs — kept
 * structural (not `UseQueryResult<T>`) so it works with any query's result
 * object without a generic type param leaking through call sites. */
export interface QueryGuardLike {
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => unknown;
}

export interface UseQueryGuardOptions {
  /** ErrorState title (e.g. "Couldn't load your board"). */
  title?: string;
  /** ErrorState message shown when `error` is NOT an ApiError. */
  fallback: string;
  /** Loading element to render instead of the default full-panel LoadingState
   * (e.g. a tab's inline <TableSkeleton />, matching its pre-hook rendering). */
  loading?: ReactNode;
  /** Extra className passed to ErrorState (e.g. a detail-rail's tighter
   * "min-h-0 py-8" instead of the full-panel min-height). */
  errorClassName?: string;
}

/** Pure decision logic behind useQueryGuard, extracted so it's unit-testable
 * without React Testing Library (this project has no component-render test
 * infra — see brain/techdebt-register-2026-07-05.md #21). Given a query-like
 * result and the guard options, returns the node to render, or null when the
 * query is ready and the caller should render its real content. */
export function queryGuardDecision(
  query: QueryGuardLike,
  { title, fallback, loading, errorClassName }: UseQueryGuardOptions,
): ReactNode | null {
  if (query.isLoading) return loading ?? <LoadingState />;
  if (query.isError) {
    return (
      <ErrorState
        title={title}
        message={
          query.error instanceof ApiError ? query.error.message : fallback
        }
        onRetry={() => query.refetch()}
        className={errorClassName}
      />
    );
  }
  return null;
}

/** Shared loading/error guard for a TanStack Query result. Replaces the
 * copy-pasted `if (query.isLoading) return <LoadingState/>; if (query.isError)
 * return <ErrorState .../>;` block duplicated across tabs — see
 * brain/techdebt-register-2026-07-05.md #21.
 *
 * Usage: `const guard = useQueryGuard(query, {title, fallback}); if (guard)
 * return guard;` — returns null when the query is ready, so the call site's
 * own render path (including empty-state checks) takes over unchanged. */
export function useQueryGuard(
  query: QueryGuardLike,
  options: UseQueryGuardOptions,
): ReactNode | null {
  return queryGuardDecision(query, options);
}
