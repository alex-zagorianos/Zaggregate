import { scoreBand, BAND_LABEL, BAND_VAR, type ScoreBand } from "@/lib/score";
import { cn } from "@/lib/utils";

/* The fit/score chip — a small pill whose color comes from the score band
 * (--zg-score-*). A dot + the numeral (mono, tabular) + an accessible label via
 * title. Unscored rows get a muted "—" pill so the column never looks broken.
 * Used by Top Picks now; Inbox (Phase 3) will reuse it. */
export function ScoreChip({
  value,
  className,
}: {
  value: number | null | undefined;
  className?: string;
}) {
  const band: ScoreBand = scoreBand(value);
  const color = BAND_VAR[band];
  const label = BAND_LABEL[band];
  const shown =
    band === "none"
      ? "—"
      : String(Math.round(typeof value === "number" ? value : Number(value)));

  return (
    <span
      title={band === "none" ? label : `${label} · ${shown}/100`}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[var(--radius-chip)] border px-2 py-0.5 text-xs font-medium",
        className,
      )}
      style={{
        color,
        borderColor: `color-mix(in oklab, ${color} 40%, transparent)`,
        backgroundColor: `color-mix(in oklab, ${color} 12%, transparent)`,
      }}
    >
      <span
        aria-hidden
        className="size-1.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      <span className="zg-num">{shown}</span>
    </span>
  );
}
