import { Ghost } from "lucide-react";

import type { GhostBadge } from "@/api/client";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/* GhostRowBadge (B7) — a subtle inline staleness marker on Inbox rows. Renders a
 * small amber "Stale"/"Aging" chip ONLY when the ghost checker flagged level
 * "stale" or "aging"; "fresh"/"unknown" render nothing. A tooltip lists the
 * reasons the checker surfaced (e.g. "posted 60d ago (stale)", "reposted"). This
 * never hides the row — it only annotates. Tokens only: amber = --zg-warn, softer
 * tint for "aging". */

export function GhostRowBadge({ ghost }: { ghost: GhostBadge | undefined }) {
  const level = ghost?.level;
  if (level !== "stale" && level !== "aging") return null;
  const reasons = (ghost?.reasons ?? []).filter(Boolean);
  const isStale = level === "stale";
  const label = isStale ? "Stale" : "Aging";
  const chip = (
    <span
      aria-label={`${label} posting`}
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-[var(--radius-chip)] border px-1.5 py-0.5 text-[0.65rem] font-medium",
        isStale
          ? "border-[var(--zg-warn)]/40 bg-[var(--zg-warn)]/10 text-[var(--zg-warn)]"
          : "border-[var(--zg-warn)]/25 bg-[var(--zg-warn)]/5 text-[var(--zg-warn)]/80",
      )}
    >
      <Ghost className="size-3" />
      {label}
    </span>
  );

  if (reasons.length === 0) return chip;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{chip}</TooltipTrigger>
      <TooltipContent>
        <ul className="space-y-0.5">
          {reasons.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      </TooltipContent>
    </Tooltip>
  );
}
