/* Faithful port of ui/theme.py::score_band — the 0–100 fit/score banding used by
 * every scored chip. Bands: good >=70, mid >=45, low >=0, none for <0 / missing /
 * non-numeric. Each band maps to a generated --zg-score-* token (kept in sync
 * with the tk palette by scripts/gen_web_tokens.py). Pure + unit-tested. */

export type ScoreBand = "good" | "mid" | "low" | "none";

export function scoreBand(value: number | null | undefined): ScoreBand {
  if (value === null || value === undefined) return "none";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n) || n < 0) return "none";
  if (n >= 70) return "good";
  if (n >= 45) return "mid";
  return "low";
}

/** Human label for a band — shown in the chip / tooltip. */
export const BAND_LABEL: Record<ScoreBand, string> = {
  good: "Strong fit",
  mid: "Possible fit",
  low: "Weak fit",
  none: "Unscored",
};

/** The --zg-score-* CSS variable for a band (drives text + tint). */
export const BAND_VAR: Record<ScoreBand, string> = {
  good: "var(--zg-score-good)",
  mid: "var(--zg-score-mid)",
  low: "var(--zg-score-low)",
  none: "var(--zg-score-none)",
};
