import * as React from "react";
import { CheckCircle2, KeyRound, Timer, XCircle, Info } from "lucide-react";

import type { SearchHealthRow } from "@/api/client";
import type { SourceStatus } from "@/lib/search-progress";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/* The end-of-run source-health strip: one chip per non-empty status bucket
 * (ok / needs key / throttled / failed) with a Details popover listing every source
 * and its outcome. Mirrors the tk SearchTab health summary line + Details popup
 * (ui/tab_search_core.health_summary_line / health_details_text), so the web and tk
 * reports agree. Rendered under the form after a search finishes. */

export interface SourceHealthStripProps {
  health: SearchHealthRow[];
}

const ORDER: SourceStatus[] = ["ok", "keyless", "throttled", "failed"];

const META: Record<
  SourceStatus,
  { label: string; icon: React.ReactNode; cls: string }
> = {
  ok: {
    label: "ok",
    icon: <CheckCircle2 className="size-3.5" />,
    cls: "text-[var(--zg-success)] border-[var(--zg-success)]/40 bg-[var(--zg-success)]/10",
  },
  keyless: {
    label: "need a key",
    icon: <KeyRound className="size-3.5" />,
    cls: "text-[var(--zg-warn)] border-[var(--zg-warn)]/40 bg-[var(--zg-warn)]/10",
  },
  throttled: {
    label: "throttled",
    icon: <Timer className="size-3.5" />,
    cls: "text-[var(--zg-warn)] border-[var(--zg-warn)]/40 bg-[var(--zg-warn)]/10",
  },
  failed: {
    label: "failed",
    icon: <XCircle className="size-3.5" />,
    cls: "text-destructive border-destructive/40 bg-destructive/10",
  },
};

export function SourceHealthStrip({ health }: SourceHealthStripProps) {
  const counts = React.useMemo(() => {
    const c: Record<SourceStatus, number> = {
      ok: 0,
      keyless: 0,
      throttled: 0,
      failed: 0,
    };
    for (const r of health) {
      const s = (r.status || "failed") as SourceStatus;
      c[s] = (c[s] ?? 0) + 1;
    }
    return c;
  }, [health]);

  if (health.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-muted-foreground text-xs font-medium">
        Sources:
      </span>
      {ORDER.filter((s) => counts[s] > 0).map((s) => (
        <span
          key={s}
          className={cn(
            "inline-flex items-center gap-1 rounded-[var(--radius-chip)] border px-1.5 py-0.5 text-xs font-medium",
            META[s].cls,
          )}
        >
          {META[s].icon}
          <span className="zg-num">{counts[s]}</span>
          {META[s].label}
        </span>
      ))}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground hover:text-foreground h-6 gap-1 px-1.5 text-xs"
          >
            <Info className="size-3.5" />
            Details
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-72">
          <DropdownMenuLabel>Per-source results</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <ul className="max-h-64 space-y-0.5 overflow-y-auto px-1 py-1">
            {[...health]
              .sort((a, b) => (a.source || "").localeCompare(b.source || ""))
              .map((r) => (
                <li
                  key={r.source}
                  className="flex items-center justify-between gap-3 px-1.5 py-1 text-sm"
                >
                  <span className="text-foreground truncate">
                    {sourceDisplay(r.source)}
                  </span>
                  <SourceOutcome row={r} />
                </li>
              ))}
          </ul>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

function SourceOutcome({ row }: { row: SearchHealthRow }) {
  const s = (row.status || "failed") as SourceStatus;
  if (row.skipped_keyless || s === "keyless") {
    return (
      <span className="text-[var(--zg-warn)] shrink-0 text-xs">
        needs a free key
      </span>
    );
  }
  if (s === "throttled") {
    return (
      <span className="text-[var(--zg-warn)] shrink-0 text-xs">throttled</span>
    );
  }
  if (row.ok) {
    return (
      <span className="zg-num text-muted-foreground shrink-0 text-xs">
        {row.count} result{row.count === 1 ? "" : "s"}
      </span>
    );
  }
  return (
    <span
      className="text-destructive max-w-[10rem] shrink-0 truncate text-xs"
      title={row.error || "unknown error"}
    >
      {row.error || "failed"}
    </span>
  );
}

function sourceDisplay(source: string): string {
  return source.replace(/Client$/i, "") || source;
}
