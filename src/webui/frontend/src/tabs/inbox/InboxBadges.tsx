import { useNavigate } from "react-router-dom";
import { Clock, Radar, Sparkles, KeyRound } from "lucide-react";

import type { InboxBadges as Badges } from "@/api/client";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import { relTime } from "@/lib/relative-time";
import { cn } from "@/lib/utils";

/* The header badge strip under the Inbox title: the last-run summary (when + how
 * many added, with a keyless-skipped chip that links to Sources), the coverage
 * reach line, and the DEMO banner. Each is best-effort — the backend returns null
 * for any piece it couldn't compute, and we simply omit it. */

export function InboxBadges({ badges }: { badges: Badges | undefined }) {
  // NOTE: the plan asks for a "hide demo rows" action wired to a retire_demo
  // endpoint "if the backend shipped one". It did NOT — the Phase 3 backend has no
  // retire-demo route (demo is a read-only badge flag; the sample inbox clears
  // itself on the first real run). So the DEMO pill is informational only, with a
  // tooltip explaining that it self-clears. Deviation noted in the delivery report.
  const navigate = useNavigate();
  if (!badges) return null;
  const { last_run, reach, demo } = badges;

  const hasKeyless = (last_run?.keyless_skipped?.length ?? 0) > 0;

  return (
    <div className="mt-4 flex flex-wrap items-center gap-2">
      {last_run && (
        <BadgePill icon={<Clock className="size-3.5" />} tone="muted">
          <span className="text-muted-foreground">Last run</span>{" "}
          <span className="text-foreground">{relTime(last_run.timestamp)}</span>
          <span className="text-muted-foreground"> · </span>
          <span className="zg-num text-foreground">{last_run.added}</span>
          <span className="text-muted-foreground"> added</span>
        </BadgePill>
      )}

      {hasKeyless && (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={() => navigate("/sources")}
              className="focus-visible:ring-ring/50 rounded-[var(--radius-chip)] outline-none focus-visible:ring-2"
            >
              <BadgePill icon={<KeyRound className="size-3.5" />} tone="warn">
                <span className="zg-num">
                  {last_run!.keyless_skipped.length}
                </span>{" "}
                source{last_run!.keyless_skipped.length === 1 ? "" : "s"}{" "}
                skipped — add a key
              </BadgePill>
            </button>
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">
            Skipped for a missing key: {last_run!.keyless_skipped.join(", ")}.
            Click to connect them.
          </TooltipContent>
        </Tooltip>
      )}

      {reach && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span>
              <BadgePill icon={<Radar className="size-3.5" />} tone="muted">
                {reach.line}
              </BadgePill>
            </span>
          </TooltipTrigger>
          {reach.reason && (
            <TooltipContent className="max-w-xs">{reach.reason}</TooltipContent>
          )}
        </Tooltip>
      )}

      {demo && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span>
              <BadgePill icon={<Sparkles className="size-3.5" />} tone="accent">
                Sample data shown
              </BadgePill>
            </span>
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">
            These are example jobs so the Inbox isn't empty before your first
            run. They clear automatically once you update your Inbox.
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}

function BadgePill({
  icon,
  tone,
  children,
}: {
  icon: React.ReactNode;
  tone: "muted" | "warn" | "accent";
  children: React.ReactNode;
}) {
  const cls =
    tone === "warn"
      ? "border-[var(--zg-warn)]/40 bg-[var(--zg-warn)]/10 text-[var(--zg-warn)]"
      : tone === "accent"
        ? "border-primary/40 bg-primary/10 text-primary"
        : "border-border bg-card text-muted-foreground";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[var(--radius-chip)] border px-2.5 py-1 text-xs",
        cls,
      )}
    >
      {icon}
      <span>{children}</span>
    </span>
  );
}
