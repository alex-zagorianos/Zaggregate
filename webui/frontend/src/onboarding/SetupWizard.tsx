import * as React from "react";
import { toast } from "sonner";
import { ArrowRight, ArrowLeft, Check, SkipForward } from "lucide-react";

import { endpoints, ApiError, type OnboardingPrefill } from "@/api/client";
import { useApplyOnboarding } from "@/api/queries";
import {
  WIZARD_STEPS,
  FINISH_INDEX,
  EMPTY_ANSWERS,
  canAdvance,
  nextIndex,
  prevIndex,
  stepState,
  answersToPayload,
  industryToPickerValue,
  FIELD_OTHER,
  type WizardAnswers,
} from "@/lib/wizard-steps";
import { ZagMark } from "@/components/zag-mark";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { WelcomeStep } from "./steps/WelcomeStep";
import { AiOfferStep } from "./steps/AiOfferStep";
import { RolesStep } from "./steps/RolesStep";
import { WhereStep } from "./steps/WhereStep";
import { ResumeStep } from "./steps/ResumeStep";
import { SourcesStep } from "./steps/SourcesStep";
import { FinishStep } from "./steps/FinishStep";

/* The onboarding takeover — a full-screen, first-run guided setup. Seven steps
 * (see lib/wizard-steps): Welcome → AI express lane offer → Roles → Where →
 * Résumé → Connect sources → Finish. A left progress rail, Back/Next/Skip, per-
 * step validation, prefill from GET /api/onboarding, and a Finish that POSTs the
 * answers and hands control back to the app (lands on the Inbox with a welcome
 * toast).
 *
 * This is the app's first impression, so it's designed, not just functional:
 * generous whitespace, a serif hero, staggered step transitions, the brand mark
 * anchoring the rail. The AI express lane (step 2) can short-circuit the whole
 * flow — applying an AI block marks onboarding done and calls onComplete. */

export interface SetupWizardProps {
  prefill: OnboardingPrefill;
  /** Called when onboarding is complete (manual finish OR AI express apply) —
   * the app closes the takeover and shows the Inbox. */
  onComplete: (opts?: { viaAi?: boolean }) => void;
  /** Called when the user chooses to skip onboarding entirely (explore first).
   * The takeover closes WITHOUT marking onboarded, so it reappears next launch. */
  onSkip: () => void;
}

export function SetupWizard({ prefill, onComplete, onSkip }: SetupWizardProps) {
  const [index, setIndex] = React.useState(0);
  const [answers, setAnswers] = React.useState<WizardAnswers>(() =>
    seedAnswers(prefill),
  );
  const applyMut = useApplyOnboarding();

  const patch = React.useCallback(
    (p: Partial<WizardAnswers>) => setAnswers((a) => ({ ...a, ...p })),
    [],
  );

  const step = WIZARD_STEPS[index];
  const isFinish = index === FINISH_INDEX;
  const advanceOk = canAdvance(index, answers);

  const goNext = () => {
    const n = nextIndex(index, answers);
    if (n === index && !isFinish) {
      // Blocked by validation — nudge the roles step.
      toast("Add at least one role", {
        description: "Tell us what kind of work you're looking for.",
      });
      return;
    }
    setIndex(n);
  };
  const goBack = () => setIndex(prevIndex(index));

  // Jump straight to Finish, keeping whatever's entered.
  const skipToFinish = () => setIndex(FINISH_INDEX);

  const finish = (buildListOptIn: boolean) => {
    const payload = answersToPayload({ ...answers, buildListOptIn });
    applyMut.mutate(payload, {
      onSuccess: (res) => {
        onComplete();
        toast.success("You're all set", {
          description: res.resume_restructured
            ? "Your résumé was tidied up for scoring. Welcome to Zaggregate!"
            : "Welcome to Zaggregate — here's your inbox.",
        });
        // A Build-My-List opt-in is a courtesy hand-off; fire-and-forget so the
        // finish isn't blocked on it. The engine serializes it behind the mutex.
        if (buildListOptIn) {
          endpoints
            .buildCompanyList({ use_inbox: true, seed_metro: true })
            .catch(() => {
              /* non-fatal — the user can run it from the palette later */
            });
        }
      },
      onError: (e) =>
        toast.error("Couldn't save your setup", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
    });
  };

  return (
    <div className="bg-background fixed inset-0 z-50 flex flex-col overflow-y-auto">
      <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-5 py-6 sm:px-8 sm:py-10">
        {/* Top: brand + skip */}
        <div className="mb-8 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <ZagMark className="text-primary size-7" />
            <span className="zg-serif text-foreground text-lg font-semibold tracking-tight">
              <span className="text-primary">Zag</span>gregate
            </span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            onClick={onSkip}
          >
            <SkipForward className="size-3.5" />
            Skip for now
          </Button>
        </div>

        <div className="grid flex-1 grid-cols-1 gap-10 md:grid-cols-[13rem_1fr]">
          {/* Progress rail */}
          <ProgressRail index={index} answers={answers} onJump={setIndex} />

          {/* Step body */}
          <div className="flex min-h-0 flex-col">
            <div
              key={step.id}
              className="animate-in fade-in-0 slide-in-from-right-2 flex-1 duration-300"
            >
              <StepBody
                step={step.id}
                answers={answers}
                patch={patch}
                onUseAi={() => onComplete({ viaAi: true })}
                onContinueManual={goNext}
                onFinish={finish}
                finishing={applyMut.isPending}
              />
            </div>

            {/* Nav — hidden on Finish (Finish has its own primary button) */}
            {!isFinish && (
              <div className="border-border mt-8 flex items-center justify-between gap-3 border-t pt-5">
                <Button
                  variant="ghost"
                  onClick={goBack}
                  disabled={index === 0}
                  className={cn(index === 0 && "invisible")}
                >
                  <ArrowLeft className="size-4" />
                  Back
                </Button>
                <div className="flex items-center gap-2">
                  {index > 0 && (
                    <Button
                      variant="outline"
                      onClick={skipToFinish}
                      className="text-muted-foreground"
                    >
                      Skip the rest
                    </Button>
                  )}
                  <Button
                    onClick={goNext}
                    disabled={!advanceOk && step.id === "roles"}
                  >
                    Next
                    <ArrowRight className="size-4" />
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── the progress rail ─────────────────────────────────────────────────────────

function ProgressRail({
  index,
  answers,
  onJump,
}: {
  index: number;
  answers: WizardAnswers;
  onJump: (i: number) => void;
}) {
  return (
    <nav aria-label="Setup progress" className="hidden md:block">
      <ol className="space-y-1">
        {WIZARD_STEPS.map((s, i) => {
          const state = stepState(i, index, answers);
          // Let the user jump BACK to any earlier step, or to the current; not
          // forward past an unvalidated gate.
          const reachable = i <= index;
          return (
            <li key={s.id}>
              <button
                type="button"
                disabled={!reachable}
                onClick={() => reachable && onJump(i)}
                className={cn(
                  "flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-left text-sm transition-colors",
                  reachable && "hover:bg-secondary/60",
                  state === "active"
                    ? "text-foreground font-medium"
                    : "text-muted-foreground",
                  !reachable && "cursor-default opacity-60",
                )}
              >
                <span
                  className={cn(
                    "zg-num flex size-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold transition-colors",
                    state === "done"
                      ? "border-primary bg-primary text-primary-foreground"
                      : state === "active"
                        ? "border-primary text-primary"
                        : "border-border text-muted-foreground",
                  )}
                >
                  {state === "done" ? <Check className="size-3.5" /> : i + 1}
                </span>
                {s.label}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

// ── step routing ──────────────────────────────────────────────────────────────

function StepBody({
  step,
  answers,
  patch,
  onUseAi,
  onContinueManual,
  onFinish,
  finishing,
}: {
  step: (typeof WIZARD_STEPS)[number]["id"];
  answers: WizardAnswers;
  patch: (p: Partial<WizardAnswers>) => void;
  onUseAi: () => void;
  onContinueManual: () => void;
  onFinish: (buildListOptIn: boolean) => void;
  finishing: boolean;
}) {
  switch (step) {
    case "welcome":
      return <WelcomeStep />;
    case "ai-offer":
      return (
        <AiOfferStep onUseAi={onUseAi} onContinueManual={onContinueManual} />
      );
    case "roles":
      return <RolesStep answers={answers} patch={patch} />;
    case "where":
      return <WhereStep answers={answers} patch={patch} />;
    case "resume":
      return <ResumeStep answers={answers} patch={patch} />;
    case "sources":
      return <SourcesStep />;
    case "finish":
      return (
        <FinishStep
          answers={answers}
          onFinish={onFinish}
          finishing={finishing}
        />
      );
    default:
      return null;
  }
}

// ── prefill → answers seed ────────────────────────────────────────────────────

function seedAnswers(prefill: OnboardingPrefill): WizardAnswers {
  const picker = industryToPickerValue(prefill.industry || "");
  return {
    ...EMPTY_ANSWERS,
    roles: prefill.roles || "",
    industry: picker,
    // If the prefill mapped to the "Other" sentinel, stash the raw text so the
    // free-text box shows it pre-filled.
    industryOther: picker === FIELD_OTHER ? prefill.industry || "" : "",
    location: prefill.location || "",
    remoteOk: prefill.remote_ok ?? true,
    salaryText: prefill.salary_min || "",
    about: prefill.about || "",
    level: prefill.level || "",
  };
}
