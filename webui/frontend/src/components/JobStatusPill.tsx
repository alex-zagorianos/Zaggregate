import * as React from "react";
import { Loader2, CheckCircle2, XCircle, Ban } from "lucide-react";

import { type JobStatus } from "@/api/client";
import { cn } from "@/lib/utils";

/* The job-status pill shared by every run console (Inbox daily-run drawer,
 * Search progress drawer, …). Extracted from the two consoles that had drifted
 * copies so a change to the running/done/cancelled/failed visual states lands in
 * one place. Keyed on the client's `JobStatus` union, styled off the Aegean
 * tokens (no raw hex/grays). */
export function JobStatusPill({ status }: { status: JobStatus }) {
  const map: Record<
    JobStatus,
    { label: string; icon: React.ReactNode; cls: string }
  > = {
    running: {
      label: "Running",
      icon: <Loader2 className="size-3 animate-spin" />,
      cls: "text-primary border-primary/40 bg-primary/10",
    },
    done: {
      label: "Done",
      icon: <CheckCircle2 className="size-3" />,
      cls: "text-[var(--zg-success)] border-[var(--zg-success)]/40 bg-[var(--zg-success)]/12",
    },
    cancelled: {
      label: "Cancelled",
      icon: <Ban className="size-3" />,
      cls: "text-muted-foreground border-border bg-secondary",
    },
    failed: {
      label: "Failed",
      icon: <XCircle className="size-3" />,
      cls: "text-destructive border-destructive/40 bg-destructive/10",
    },
  };
  const s = map[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-[var(--radius-chip)] border px-1.5 py-0.5 text-[0.7rem] font-medium",
        s.cls,
      )}
    >
      {s.icon}
      {s.label}
    </span>
  );
}
