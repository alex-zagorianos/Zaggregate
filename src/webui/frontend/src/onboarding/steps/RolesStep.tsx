import { Briefcase } from "lucide-react";

import {
  FIELD_PRESETS,
  FIELD_OTHER,
  parseRoles,
  type WizardAnswers,
} from "@/lib/wizard-steps";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { StepHead } from "./StepHead";

/* Step 3 — Roles. The one gating step: needs ≥1 role. A comma-separated roles box
 * (with a live chip preview so the user sees how it splits) plus a validated field
 * picker that emits a canonical industry token (or "Other" → a free-text box). The
 * field preset turns on non-generic source routing + query synonyms server-side. */

export function RolesStep({
  answers,
  patch,
}: {
  answers: WizardAnswers;
  patch: (p: Partial<WizardAnswers>) => void;
}) {
  const roleChips = parseRoles(answers.roles);
  const isOther = answers.industry === FIELD_OTHER;

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
          <Label htmlFor="wiz-field" className="text-foreground text-sm">
            Your field{" "}
            <span className="text-muted-foreground font-normal">
              (optional)
            </span>
          </Label>
          <Select
            id="wiz-field"
            value={answers.industry}
            onChange={(e) => patch({ industry: e.target.value })}
            className="h-11"
          >
            <option value="">Choose a field…</option>
            {FIELD_PRESETS.map((p) => (
              <option key={p.token} value={p.token}>
                {p.label}
              </option>
            ))}
            <option value={FIELD_OTHER}>Other (type your own)…</option>
          </Select>
          <p className="text-muted-foreground text-xs">
            Picking a field turns on smarter, field-specific job sources.
          </p>
          {isOther && (
            <Input
              value={answers.industryOther}
              onChange={(e) => patch({ industryOther: e.target.value })}
              placeholder="Type your field, e.g. biomedical engineering"
              autoComplete="off"
              className="mt-2"
            />
          )}
        </div>
      </div>
    </div>
  );
}
