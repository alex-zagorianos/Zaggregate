import { HeartCrack } from "lucide-react";

import type { GhostedBefore } from "@/api/client";

/* GhostedBeforeNote (B7 item 3) — "This company left you on read before." A warm,
 * read-only reminder shown in the Inbox detail pane and the JobDialog when the user
 * has at least one application to this company they marked "ghosted". Renders
 * nothing when there's no such history. Not a warning banner — a gentle heads-up,
 * so the user can weigh where to spend effort. Amber tint (--zg-warn), soft. */

export function GhostedBeforeNote({
  before,
}: {
  before: GhostedBefore | undefined;
}) {
  const count = before?.count ?? 0;
  if (count <= 0) return null;
  const times = count === 1 ? "once" : `${count}×`;
  return (
    <div className="flex items-start gap-2.5 rounded-md border border-[var(--zg-warn)]/30 bg-[var(--zg-warn)]/8 px-3 py-2.5 text-sm leading-relaxed text-[var(--zg-warn)]">
      <HeartCrack className="mt-0.5 size-4 shrink-0" />
      <span>
        This company left you on read before ({times}). Worth a warm path in —
        or a second thought.
      </span>
    </div>
  );
}
