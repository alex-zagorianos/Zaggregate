/* The onboarding-wizard state machine — pure, testable, UI-free.
 *
 * The wizard is a 7-step guided flow (the web twin of ui/setup_wizard.py). This
 * module owns the STEP MODEL and the answer VALIDATION so the React component is
 * just presentation + endpoint calls: it holds an `answers` object + a `stepIndex`
 * and asks this module "can I advance?" / "which steps are done?".
 *
 * The steps mirror the tk wizard's screens (with the extra AI express-lane offer
 * as step 2):
 *   0 welcome          — intro, no input (always valid)
 *   1 ai-offer         — offer the AI express lane OR continue manually (valid)
 *   2 roles            — the roles/keywords + field preset (needs ≥1 role)
 *   3 where            — location + remote + salary floor (valid; all optional)
 *   4 resume           — paste résumé (optional; preview via structure endpoint)
 *   5 sources          — connect job sources (embeds SourcesTab; always valid)
 *   6 finish           — daily-updates note + Build-My-List opt-in (valid)
 *
 * "Skip" jumps straight to Finish with whatever's entered; the field presets +
 * level vocabulary come from setup_wizard_core (kept in sync here as a typed
 * mirror — the server re-validates on apply, this is just for the picker).
 */

export type WizardStepId =
  "welcome" | "ai-offer" | "roles" | "where" | "resume" | "sources" | "finish";

export interface WizardStep {
  id: WizardStepId;
  /** Short label for the progress rail. */
  label: string;
}

/** The ordered step list — the single source of truth for the rail + navigation. */
export const WIZARD_STEPS: readonly WizardStep[] = [
  { id: "welcome", label: "Welcome" },
  { id: "ai-offer", label: "Quick setup" },
  { id: "roles", label: "Roles" },
  { id: "where", label: "Where" },
  { id: "resume", label: "Résumé" },
  { id: "sources", label: "Sources" },
  { id: "finish", label: "Finish" },
] as const;

export const WIZARD_STEP_COUNT = WIZARD_STEPS.length;
/** The index of the terminal step (where Finish is offered). */
export const FINISH_INDEX = WIZARD_STEP_COUNT - 1;

/** The wizard answers the component accumulates. `roles` is the raw comma-string
 * the user types (split on apply); `salaryText` is free-text (annualized server-
 * side); `industry`/`level` are canonical preset values. */
export interface WizardAnswers {
  roles: string;
  /** The field-preset picker value: a preset token, the FIELD_OTHER sentinel, or
   * "". When it's FIELD_OTHER, `industryOther` holds the free-text field. */
  industry: string;
  /** Free-text field, used only when `industry === FIELD_OTHER`. */
  industryOther: string;
  location: string;
  remoteOk: boolean;
  salaryText: string;
  resumeText: string;
  level: string;
  about: string;
  buildListOptIn: boolean;
}

export const EMPTY_ANSWERS: WizardAnswers = {
  roles: "",
  industry: "",
  industryOther: "",
  location: "",
  remoteOk: true,
  salaryText: "",
  resumeText: "",
  level: "",
  about: "",
  buildListOptIn: false,
};

/** Split the roles comma-string into a trimmed, de-duplicated list (the same
 * shape the server's _answers_from_body builds). Empty tokens are dropped. */
export function parseRoles(roles: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of roles.split(",")) {
    const r = raw.trim();
    if (!r) continue;
    const key = r.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(r);
  }
  return out;
}

/** Whether a single step's inputs are complete enough to advance. Only Roles
 * gates (needs ≥1 role); every other step is always satisfiable (inclusion over
 * precision — we never block onboarding on an optional field). */
export function isStepValid(
  step: WizardStepId,
  answers: WizardAnswers,
): boolean {
  switch (step) {
    case "roles":
      return parseRoles(answers.roles).length > 0;
    default:
      return true;
  }
}

/** Can the user advance FROM the step at `index`? False past the last step. */
export function canAdvance(index: number, answers: WizardAnswers): boolean {
  if (index < 0 || index >= WIZARD_STEP_COUNT) return false;
  return isStepValid(WIZARD_STEPS[index].id, answers);
}

/** Whether a step is "complete" for the progress rail's checkmarks. A step is
 * complete when it's valid AND the user has moved past it (index < current);
 * the current step shows as active, later steps as pending. */
export function stepState(
  index: number,
  currentIndex: number,
  answers: WizardAnswers,
): "done" | "active" | "pending" {
  if (index === currentIndex) return "active";
  if (index < currentIndex && isStepValid(WIZARD_STEPS[index].id, answers))
    return "done";
  return "pending";
}

/** The next index, clamped; returns the same index when it can't advance (an
 * invalid step) or when already at Finish. */
export function nextIndex(index: number, answers: WizardAnswers): number {
  if (!canAdvance(index, answers)) return index;
  return Math.min(FINISH_INDEX, index + 1);
}

/** The previous index, clamped at 0. Back never validates (you can always
 * retreat). */
export function prevIndex(index: number): number {
  return Math.max(0, index - 1);
}

/** Resolve the industry to the canonical token to send: the free-text
 * `industryOther` when the picker is on "Other", otherwise the picker value
 * itself (a preset token or ""). */
export function resolveIndustry(answers: WizardAnswers): string {
  if (answers.industry === FIELD_OTHER) return answers.industryOther.trim();
  return answers.industry.trim();
}

/** Map the accumulated answers into the OnboardingAnswers POST body shape the
 * server expects (roles → list, salary → free-text string passed through). Pure
 * so it's unit-testable against the server contract. */
export function answersToPayload(answers: WizardAnswers): {
  roles: string[];
  location: string;
  remote_ok: boolean;
  salary_min: string;
  industry: string;
  level: string;
  about: string;
  resume_text: string;
} {
  return {
    roles: parseRoles(answers.roles),
    location: answers.location.trim(),
    remote_ok: answers.remoteOk,
    salary_min: answers.salaryText.trim(),
    industry: resolveIndustry(answers),
    level: answers.level.trim(),
    about: answers.about.trim(),
    resume_text: answers.resumeText,
  };
}

// ── field-preset + level vocabulary (mirror of setup_wizard_core) ──────────────
// Kept in sync with ui/setup_wizard_core._FIELD_PRESETS / _LEVELS. The server
// re-validates on apply; this is only the picker's option list. The "Other"
// sentinel keeps the free-text escape hatch (reach is never reduced).

/** The "Other (type your own)" sentinel — selecting it reveals a free-text box. */
export const FIELD_OTHER = "__other__";

export interface FieldPreset {
  /** The dropdown label. */
  label: string;
  /** The canonical industry token emitted (empty for "Other"). */
  token: string;
}

export const FIELD_PRESETS: readonly FieldPreset[] = [
  { label: "Software engineering", token: "software engineering" },
  { label: "Mechanical engineering", token: "mechanical engineering" },
  { label: "Controls / automation engineering", token: "controls engineering" },
  { label: "Data analytics / data science", token: "data analytics" },
  { label: "Consulting", token: "consulting" },
  { label: "Marketing", token: "marketing" },
  { label: "Warehouse / logistics", token: "warehouse logistics" },
  { label: "Teaching / education (K-12)", token: "education" },
  { label: "Nursing / healthcare", token: "nursing" },
  { label: "Finance / accounting", token: "finance" },
] as const;

/** The career-level options (mirror of _LEVELS; "" = leave defaults). */
export const LEVEL_OPTIONS: readonly string[] = [
  "",
  "Entry",
  "Mid",
  "Senior",
  "Manager/Exec",
] as const;

/** Resolve an incoming industry token (from prefill) to the picker value: a
 * known preset's token stays as-is; a non-empty unknown token maps to the
 * "Other" sentinel (so the free-text box shows, pre-filled); blank stays blank. */
export function industryToPickerValue(industry: string): string {
  const ind = (industry || "").trim().toLowerCase();
  if (!ind) return "";
  const hit = FIELD_PRESETS.find((p) => p.token.toLowerCase() === ind);
  return hit ? hit.token : FIELD_OTHER;
}
