import { Zap, ArrowRight } from "lucide-react";

import { AiSetupPanes, type AiSetupResult } from "@/components/ai-setup-dialog";

/* Step 0 — the AI-first landing (S40). This is the app's first impression and the
 * fast path: copy ONE prompt, paste it into your AI above your résumé + one
 * sentence, paste the reply back — and roles, location, salary, starter companies
 * AND your first search all come from that single paste. The express lane is
 * embedded INLINE (AiSetupPanes, promptKind "full", autorun true) rather than
 * behind a dialog, so it IS the screen. A quiet link drops into the manual steps
 * for anyone who'd rather answer the questions by hand.
 *
 * On a successful apply, `onApplied` fires with the full result (job_id +
 * seed_count): the wizard closes the takeover and lands the user on the Inbox with
 * the first-run console attached. */

export function StartStep({
  onApplied,
  onManual,
}: {
  /** Fired after the combined AI reply applies (carries job_id/seed_count). */
  onApplied: (res: AiSetupResult) => void;
  /** Fired when the user chooses to fill the wizard out by hand → the Roles step. */
  onManual: () => void;
}) {
  return (
    <div className="max-w-2xl">
      <p className="text-primary mb-3 flex items-center gap-2 text-sm font-medium tracking-wide uppercase">
        <Zap className="size-4" />
        The fast way
      </p>
      <h1 className="zg-serif text-foreground text-3xl leading-tight font-semibold tracking-tight sm:text-4xl">
        Let your AI set you up
      </h1>
      <p className="text-muted-foreground mt-4 max-w-[52ch] text-lg leading-relaxed">
        Copy one prompt, paste it into your AI above your résumé and one
        sentence about the work you want, then paste the reply back — roles,
        location, salary, starter companies, and your first search, all from one
        paste.
      </p>

      <div className="mt-8 space-y-4">
        <AiSetupPanes promptKind="full" autorun={true} onApplied={onApplied} />
      </div>

      {/* Quiet escape hatch into the manual steps — reach is never reduced. */}
      <div className="border-border mt-8 border-t pt-5">
        <button
          type="button"
          onClick={onManual}
          className="text-muted-foreground hover:text-foreground group inline-flex items-center gap-1.5 text-sm font-medium transition-colors"
        >
          I'd rather fill it in myself
          <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
        </button>
      </div>
    </div>
  );
}
