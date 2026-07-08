import { Briefcase } from "lucide-react";

import {
  FIELD_OTHER,
  parseRoles,
  type WizardAnswers,
} from "@/lib/wizard-steps";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  KeywordPoolPanel,
  mergeTermsCsv,
} from "@/tabs/search/KeywordPoolPanel";
import { StepHead } from "./StepHead";

/* Step 3 — Roles. The one gating step: needs ≥1 role. A comma-separated roles
 * box (with a live chip preview so the user sees how it splits) as the direct,
 * typed-by-hand path, plus the KeywordPoolPanel (Search Discovery,
 * search-discovery-plan.md §4.4) as the DEFAULT keyword-picking view — the
 * richer, guided alternative that replaces the old fixed field-preset <select>.
 * Activating a chip there folds into `roles` (union merge, never clobbers what
 * was typed); submitting a field there sets `industry` directly from the free
 * text (industry_profile.resolve() isn't limited to a fixed list either). */

export function RolesStep({
  answers,
  patch,
}: {
  answers: WizardAnswers;
  patch: (p: Partial<WizardAnswers>) => void;
}) {
  const roleChips = parseRoles(answers.roles);
  const initialField =
    answers.industry === FIELD_OTHER
      ? answers.industryOther
      : answers.industry || parseRoles(answers.roles)[0] || "";

  return (
    <div className="max-w-2xl">
      <StepHead
        icon={<Briefcase className="size-4" />}
        eyebrow="About the work"
        title="What kind of roles are you after?"
        sub="List the titles or keywords you care about. Be generous — you can always narrow later."
      />

      <div className="mt-8 space-y-6">
        <div className="space-y-2">
          <Label htmlFor="wiz-roles" className="text-foreground text-sm">
            Roles or keywords
            <span className="text-destructive ml-0.5">*</span>
          </Label>
          <Input
            id="wiz-roles"
            value={answers.roles}
            onChange={(e) => patch({ roles: e.target.value })}
            placeholder="e.g. mechanical engineer, design engineer, R&D"
            autoComplete="off"
            autoFocus
            className="h-11 text-base"
          />
          <p className="text-muted-foreground text-xs">
            Separate several with commas.
          </p>
          {roleChips.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {roleChips.map((r) => (
                <Badge key={r} variant="accent">
                  {r}
                </Badge>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-2">
          <Label className="text-foreground text-sm">
            Find keywords for your field{" "}
            <span className="text-muted-foreground font-normal">
              (optional)
            </span>
          </Label>
          <KeywordPoolPanel
            alwaysOpen
            initialField={initialField}
            resumeText={answers.resumeText}
            onFieldChange={(field) =>
              patch({ industry: field, industryOther: "" })
            }
            onActiveTermsChange={(csv) =>
              patch({ roles: mergeTermsCsv(answers.roles, csv) })
            }
          />
        </div>
      </div>
    </div>
  );
}
