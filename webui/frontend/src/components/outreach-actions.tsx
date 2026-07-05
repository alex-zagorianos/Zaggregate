import * as React from "react";
import { toast } from "sonner";
import { Mail, MessageSquareText, Loader2 } from "lucide-react";

import { endpoints } from "@/api/client";
import { friendlyError } from "@/lib/friendly-error";
import { hasInterviewHappened } from "@/lib/outreach-stage";
import { PromptDialog } from "@/components/prompt-dialog";
import { Button } from "@/components/ui/button";

/* "Outreach" — the follow-up / thank-you + interview-prep surface in the JobDialog
 * (B5). Two BYO-AI, prompt-only actions:
 *
 *   - "Draft follow-up" builds a post-application nudge; its label flips to
 *     "Draft thank-you" once an interview has happened (a round is logged or the
 *     status is at/past an interview stage), matching the note the backend will
 *     actually draft (the backend is the source of truth — it auto-selects and
 *     returns `stage`; the label is just a best-effort client hint).
 *   - "Interview prep" builds a practice brief grounded in the user's experience.
 *
 * Both open a read-only PromptDialog the user copies into whatever AI they use. */

export interface OutreachActionsProps {
  appId: number;
  status: string;
  /** Number of interview rounds logged — drives the follow-up/thank-you label. */
  roundCount: number;
}

export function OutreachActions({
  appId,
  status,
  roundCount,
}: OutreachActionsProps) {
  const [prompt, setPrompt] = React.useState("");
  const [dialogTitle, setDialogTitle] = React.useState("");
  const [dialogDesc, setDialogDesc] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const [busy, setBusy] = React.useState<"followup" | "prep" | null>(null);

  const thankYou = hasInterviewHappened(status, roundCount);
  const followupLabel = thankYou ? "Draft thank-you" : "Draft follow-up";

  const draftFollowup = React.useCallback(() => {
    setBusy("followup");
    endpoints
      .appFollowupPrompt(appId)
      .then((r) => {
        setPrompt(r.prompt);
        const isThanks = r.stage === "thank_you";
        setDialogTitle(isThanks ? "Thank-you note" : "Follow-up note");
        setDialogDesc(
          isThanks
            ? "Copy this into your AI. It drafts a short, sincere thank-you to send within 24 hours."
            : "Copy this into your AI. It drafts one warm, no-groveling follow-up — send it just once.",
        );
        setOpen(true);
      })
      .catch((e) =>
        toast.error("Couldn't build the note", {
          description: friendlyError(e),
        }),
      )
      .finally(() => setBusy(null));
  }, [appId]);

  const draftPrep = React.useCallback(() => {
    setBusy("prep");
    endpoints
      .appInterviewPrepPrompt(appId)
      .then((r) => {
        setPrompt(r.prompt);
        setDialogTitle("Interview prep");
        setDialogDesc(
          "Copy this into your AI. It returns likely topics, ten practice questions, and strong-answer sketches grounded in your experience.",
        );
        setOpen(true);
      })
      .catch((e) =>
        toast.error("Couldn't build the prep brief", {
          description: friendlyError(e),
        }),
      )
      .finally(() => setBusy(null));
  }, [appId]);

  return (
    <section className="space-y-2">
      <h3 className="text-muted-foreground flex items-center gap-1.5 text-xs font-semibold tracking-wide uppercase">
        <MessageSquareText className="size-3.5" />
        Outreach
      </h3>
      <p className="text-muted-foreground text-sm leading-relaxed">
        Prompt-only helpers you copy into your own AI — a note to send, or a
        prep brief before you interview.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={draftFollowup}
          disabled={busy !== null}
        >
          {busy === "followup" ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Mail className="size-3.5" />
          )}
          {followupLabel}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={draftPrep}
          disabled={busy !== null}
        >
          {busy === "prep" ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <MessageSquareText className="size-3.5" />
          )}
          Interview prep
        </Button>
      </div>

      <PromptDialog
        open={open}
        onOpenChange={setOpen}
        title={dialogTitle}
        description={dialogDesc}
        prompt={prompt}
      />
    </section>
  );
}
