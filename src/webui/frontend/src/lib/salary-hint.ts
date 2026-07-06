/* Salary-hint formatting — the live annualization echo under the wizard's salary
 * box. The server's /api/onboarding/salary-parse returns {annual, kind}; this
 * turns that into the human line the tk wizard shows as you type
 * ("≈ $37,440 / yr from $18/hr"), so the user understands how "18" was read.
 *
 * Pure + UI-free so the component just renders the string this returns. */

import type { SalaryKind } from "@/api/client";

/** Format an integer dollar amount as "$90,000" (no cents). */
export function formatDollars(n: number): string {
  return `$${Math.round(n).toLocaleString("en-US")}`;
}

/** The hint line for a parsed salary. Returns "" when there's nothing to show
 * (blank input, or an unparseable string) so the caller can hide the line.
 *   • annual  → "Minimum: $90,000 / yr"
 *   • hourly  → "≈ $37,440 / yr  (from an hourly rate)"
 *   • none    → "" (couldn't read a number — don't nag, the field is optional)
 */
export function salaryHint(
  annual: number | null,
  kind: SalaryKind,
  rawText: string,
): string {
  const hasText = rawText.trim().length > 0;
  if (!hasText) return "";
  if (annual === null || kind === "none") {
    // The user typed something but we couldn't read a number. Gentle, not an
    // error — salary is optional (inclusion over precision).
    return "";
  }
  if (kind === "hourly") {
    return `≈ ${formatDollars(annual)} / yr  (annualized from an hourly rate)`;
  }
  return `Minimum: ${formatDollars(annual)} / yr`;
}
