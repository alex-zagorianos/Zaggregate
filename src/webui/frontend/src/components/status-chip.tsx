import { statusVar, statusLabel, statusChipStyle } from "@/lib/status";
import { cn } from "@/lib/utils";

/* The application-status chip — a small pill whose color comes from the
 * --zg-status-* token for the status (color-mixed into a tint + hairline border,
 * exactly like ScoreChip so the two read as one family). The label text is the
 * server's STATUS_LABELS value (passed in via `labels`) with a Title-Case
 * fallback. Shared by the Tracker table, the Board column headers, and the
 * JobDialog. NEVER a raw hex or a default gray — the color is always a status
 * token. */
export function StatusChip({
  status,
  labels,
  className,
  dot = true,
}: {
  status: string | null | undefined;
  labels?: Record<string, string> | null;
  className?: string;
  /** Show the leading color dot (off for the dense table variant). */
  dot?: boolean;
}) {
  const color = statusVar(status);
  const label = statusLabel(status, labels);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[var(--radius-chip)] border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        className,
      )}
      style={statusChipStyle(color)}
    >
      {dot && (
        <span
          aria-hidden
          className="size-1.5 shrink-0 rounded-full"
          style={{ backgroundColor: color }}
        />
      )}
      {label}
    </span>
  );
}
