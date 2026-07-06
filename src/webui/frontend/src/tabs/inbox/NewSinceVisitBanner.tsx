import * as React from "react";
import { Sparkles, X } from "lucide-react";

import { useStatus } from "@/api/queries";
import type { InboxRow } from "@/api/client";
import {
  readLastVisit,
  writeLastVisit,
  countNewSince,
} from "@/lib/new-since-visit";

/* "N new since your last visit" (B7 item 4) — a frontend-only, dismissable banner
 * chip. On the first load with rows present, we read the per-project last-visit
 * stamp from localStorage, count rows newer than it, and (if any) show the chip.
 * We then write a fresh stamp so a later visit compares against THIS visit. The
 * count is computed once per (project, first non-empty rows) so it doesn't flicker
 * as filters change; dismiss hides it for the session. Never blocks or hides
 * rows — pure annotation. */

export function NewSinceVisitBanner({ rows }: { rows: InboxRow[] }) {
  const status = useStatus();
  const project = status.data?.project ?? null;

  const [count, setCount] = React.useState(0);
  const [dismissed, setDismissed] = React.useState(false);
  // Guard so the count is computed once per project load (not on every rows
  // change from filtering/windowing), and the visit stamp is written exactly once.
  const stampedFor = React.useRef<string | null>(null);

  React.useEffect(() => {
    // Wait until the project is known AND some rows have loaded — an empty inbox
    // has nothing to be "new" against, and we don't want to stamp a pre-load state.
    if (project === null || rows.length === 0) return;
    if (stampedFor.current === project) return;
    stampedFor.current = project;

    const since = readLastVisit(project);
    setCount(countNewSince(rows, since));
    setDismissed(false);
    // Record this visit so the next one compares against now.
    writeLastVisit(project);
  }, [project, rows]);

  if (count <= 0 || dismissed) return null;

  return (
    <div className="border-primary/30 bg-primary/8 text-foreground mt-3 flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
      <Sparkles className="text-primary size-4 shrink-0" />
      <span>
        <span className="zg-num font-semibold">{count}</span>{" "}
        {count === 1 ? "job is" : "jobs are"} new since your last visit.
      </span>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        aria-label="Dismiss"
        className="text-muted-foreground hover:text-foreground ml-auto inline-flex items-center"
      >
        <X className="size-3.5" />
      </button>
    </div>
  );
}
