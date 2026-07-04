import * as React from "react";
import { Sparkles, PencilLine, ArrowRight, Zap } from "lucide-react";

import { AiSetupDialog } from "@/components/ai-setup-dialog";

/* Step 2 — the AI express lane offer. Two doors: hand setup to your own AI (opens
 * the AiSetupDialog; a successful apply short-circuits the whole wizard via
 * onUseAi) or set it up by hand (continue to the Roles step). Always valid — it's
 * a choice, not an input. */

export function AiOfferStep({
  onUseAi,
  onContinueManual,
}: {
  /** Fired after the AI express lane successfully applies a config. */
  onUseAi: () => void;
  /** Fired when the user chooses to fill the wizard out by hand. */
  onContinueManual: () => void;
}) {
  const [aiOpen, setAiOpen] = React.useState(false);

  return (
    <div className="max-w-2xl">
      <p className="text-primary mb-3 flex items-center gap-2 text-sm font-medium tracking-wide uppercase">
        <Zap className="size-4" />
        The fast way
      </p>
      <h2 className="zg-serif text-foreground text-3xl leading-tight font-semibold tracking-tight sm:text-4xl">
        Let your AI do the setup?
      </h2>
      <p className="text-muted-foreground mt-4 max-w-[48ch] text-lg leading-relaxed">
        Paste one prompt into claude.ai (or any chatbot) with your résumé, and
        it fills in your roles, location, salary, and seniority for you. Or set
        it up by hand — it's only a few fields.
      </p>

      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <button
          type="button"
          onClick={() => setAiOpen(true)}
          className="border-primary/40 bg-accent/40 hover:border-primary hover:bg-accent/60 group flex flex-col items-start rounded-lg border p-5 text-left transition-colors"
        >
          <div className="bg-primary text-primary-foreground mb-3 flex size-10 items-center justify-center rounded-lg">
            <Sparkles className="size-5" />
          </div>
          <h3 className="zg-serif text-foreground text-lg font-semibold tracking-tight">
            Set up with my AI
          </h3>
          <p className="text-muted-foreground mt-1 text-sm leading-relaxed">
            Fastest — copy a prompt, paste the reply, done. No key needed.
          </p>
          <span className="text-primary mt-4 inline-flex items-center gap-1 text-sm font-medium">
            Start
            <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
          </span>
        </button>

        <button
          type="button"
          onClick={onContinueManual}
          className="border-border bg-card hover:border-ring/40 hover:bg-secondary/40 group flex flex-col items-start rounded-lg border p-5 text-left transition-colors"
        >
          <div className="bg-secondary text-foreground mb-3 flex size-10 items-center justify-center rounded-lg">
            <PencilLine className="size-5" />
          </div>
          <h3 className="zg-serif text-foreground text-lg font-semibold tracking-tight">
            Fill it in myself
          </h3>
          <p className="text-muted-foreground mt-1 text-sm leading-relaxed">
            A few quick questions about the work you want.
          </p>
          <span className="text-foreground mt-4 inline-flex items-center gap-1 text-sm font-medium">
            Continue
            <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
          </span>
        </button>
      </div>

      <AiSetupDialog
        open={aiOpen}
        onOpenChange={setAiOpen}
        onApplied={() => {
          // The AI wrote the full contract + marked onboarded; close the takeover.
          setAiOpen(false);
          onUseAi();
        }}
      />
    </div>
  );
}
