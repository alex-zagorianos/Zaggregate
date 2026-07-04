import * as React from "react";
import { MapPin } from "lucide-react";

import { endpoints, type SalaryKind } from "@/api/client";
import { salaryHint } from "@/lib/salary-hint";
import { LEVEL_OPTIONS, type WizardAnswers } from "@/lib/wizard-steps";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { StepHead } from "./StepHead";

/* Step 4 — Where + pay + level. Location, a remote-OK toggle, a free-text salary
 * floor with a LIVE annualization hint (debounced call to /salary-parse, echoing
 * "≈ $37,440/yr from an hourly rate" so "18" reads correctly), and a seniority
 * picker. All optional (inclusion over precision — we never block on pay). */

export function WhereStep({
  answers,
  patch,
}: {
  answers: WizardAnswers;
  patch: (p: Partial<WizardAnswers>) => void;
}) {
  const hint = useSalaryHint(answers.salaryText);

  return (
    <div className="max-w-2xl">
      <StepHead
        icon={<MapPin className="size-4" />}
        eyebrow="Where & how much"
        title="Where do you want to work?"
        sub="A city anchors local search; remote is on by default so you never miss a remote role."
      />

      <div className="mt-8 space-y-6">
        <div className="space-y-2">
          <Label htmlFor="wiz-location" className="text-foreground text-sm">
            Location
          </Label>
          <Input
            id="wiz-location"
            value={answers.location}
            onChange={(e) => patch({ location: e.target.value })}
            placeholder="e.g. Cincinnati, OH"
            autoComplete="off"
            autoFocus
            className="h-11 text-base"
          />
          <label className="mt-2 flex w-fit cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={answers.remoteOk}
              onChange={(e) => patch({ remoteOk: e.target.checked })}
              className="accent-[var(--zg-accent)] size-4"
            />
            <span className="text-foreground">Remote roles are fine too</span>
          </label>
        </div>

        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="wiz-salary" className="text-foreground text-sm">
              Minimum salary{" "}
              <span className="text-muted-foreground font-normal">
                (optional)
              </span>
            </Label>
            <Input
              id="wiz-salary"
              value={answers.salaryText}
              onChange={(e) => patch({ salaryText: e.target.value })}
              placeholder="e.g. 90k, $85,000, or 18/hr"
              autoComplete="off"
              className="zg-num h-11"
            />
            <p
              className={
                hint
                  ? "text-primary min-h-4 text-xs"
                  : "text-muted-foreground min-h-4 text-xs"
              }
            >
              {hint || "We'll annualize hourly rates for you."}
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="wiz-level" className="text-foreground text-sm">
              Career level{" "}
              <span className="text-muted-foreground font-normal">
                (optional)
              </span>
            </Label>
            <Select
              id="wiz-level"
              value={answers.level}
              onChange={(e) => patch({ level: e.target.value })}
              className="h-11"
            >
              {LEVEL_OPTIONS.map((lvl) => (
                <option key={lvl || "any"} value={lvl}>
                  {lvl || "No preference"}
                </option>
              ))}
            </Select>
            <p className="text-muted-foreground text-xs">
              Tunes how strictly seniority is scored.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Debounced live salary hint. Calls /api/onboarding/salary-parse ~350ms after
 * the last keystroke and returns the formatted echo line (blank while empty /
 * unparseable). Aborts a stale in-flight request when the text changes. */
function useSalaryHint(text: string): string {
  const [hint, setHint] = React.useState("");

  React.useEffect(() => {
    if (!text.trim()) {
      setHint("");
      return;
    }
    let cancelled = false;
    const t = window.setTimeout(() => {
      endpoints
        .parseSalary(text)
        .then((r) => {
          if (!cancelled)
            setHint(salaryHint(r.annual, r.kind as SalaryKind, text));
        })
        .catch(() => {
          if (!cancelled) setHint("");
        });
    }, 350);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, [text]);

  return hint;
}
