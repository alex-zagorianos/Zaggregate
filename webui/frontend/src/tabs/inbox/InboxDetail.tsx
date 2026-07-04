import {
  MousePointerClick,
  ExternalLink,
  CheckCircle2,
  XCircle,
  Ghost,
  Building2,
  MapPin,
  Wallet,
  FileSearch,
  Loader2,
} from "lucide-react";

import { useInboxDetail } from "@/api/queries";
import { ApiError, type InboxRow } from "@/api/client";
import { ScoreChip } from "@/components/score-chip";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/states";
import { cn } from "@/lib/utils";

/* The detail pane — the right rail that fills when a row is selected. Everything
 * shown here is server-computed from data the pipeline already produced (no AI, no
 * network): the fit rationale, the score breakdown, a ghost/stale warning, the ATS
 * keyword hint, and a clamped description preview. Its actions (Open / Track /
 * Dismiss) mirror the row triage so the pane is a full second surface for the
 * focused job. Empty until a row is picked. */

export interface InboxDetailProps {
  /** The selected row (from the list — gives us the header instantly while the
   * detail payload loads). null = nothing selected. */
  row: InboxRow | null;
  onTrack: (row: InboxRow) => void;
  onDismiss: (row: InboxRow) => void;
  onOpen: (row: InboxRow) => void;
}

export function InboxDetail({
  row,
  onTrack,
  onDismiss,
  onOpen,
}: InboxDetailProps) {
  const detail = useInboxDetail(row?.id ?? null);

  if (!row) {
    return (
      <div className="flex min-h-[46vh] flex-col items-center justify-center px-6 text-center">
        <MousePointerClick
          className="text-muted-foreground/40 mb-4 size-10"
          strokeWidth={1.25}
        />
        <p className="zg-serif text-foreground text-lg font-medium">
          Select a job
        </p>
        <p className="text-muted-foreground mt-1.5 max-w-xs text-sm leading-relaxed">
          Pick a row to see why it matched, its score breakdown, and a preview —
          then track or dismiss it.
        </p>
      </div>
    );
  }

  const fit = fitValue(row);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-border border-b px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="zg-serif text-foreground text-lg leading-tight font-semibold tracking-tight">
              {row.title || "Untitled role"}
            </h2>
            <p className="text-muted-foreground mt-0.5 flex items-center gap-1.5 text-sm">
              <Building2 className="size-3.5 shrink-0" />
              <span className="truncate">
                {row.company || "Unknown company"}
              </span>
            </p>
          </div>
          <ScoreChip value={fit} />
        </div>

        {/* Meta line */}
        <div className="text-muted-foreground mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
          <span className="flex items-center gap-1">
            <MapPin className="size-3.5" />
            {row.location || "—"}
            {!row.computed.location_visible && (
              <span className="text-[var(--zg-warn)]"> · out of area</span>
            )}
          </span>
          {row.salary_text && (
            <span className="zg-num flex items-center gap-1">
              <Wallet className="size-3.5" />
              {row.salary_text}
            </span>
          )}
          {row.source && <span className="capitalize">{row.source}</span>}
        </div>

        {/* Actions */}
        <div className="mt-4 flex items-center gap-2">
          <Button size="sm" onClick={() => onTrack(row)}>
            <CheckCircle2 className="size-4" />
            Track
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => onOpen(row)}
            disabled={!row.url}
          >
            <ExternalLink className="size-4" />
            Open
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onDismiss(row)}
            className="text-muted-foreground hover:text-destructive"
          >
            <XCircle className="size-4" />
            Dismiss
          </Button>
        </div>
      </div>

      {/* Scrolling body */}
      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4">
        {detail.isError ? (
          <ErrorState
            title="Couldn't load details"
            message={
              detail.error instanceof ApiError
                ? detail.error.message
                : "The detail service didn't respond."
            }
            onRetry={() => detail.refetch()}
            className="min-h-0 py-8"
          />
        ) : detail.isLoading ? (
          <p className="text-muted-foreground flex items-center gap-2 text-sm">
            <Loader2 className="size-4 animate-spin" />
            Loading details…
          </p>
        ) : (
          <>
            <GhostBanner ghost={detail.data?.ghost} />

            <FitWhy fit={fit} why={detail.data?.fit_why} />

            <ScoreBreakdown notes={detail.data?.score_notes} />

            <AtsHint ats={detail.data?.ats} />

            <DescriptionPreview text={detail.data?.description_preview} />
          </>
        )}
      </div>
    </div>
  );
}

/** Lead with the AI fit when present, else the base match score (never empty for a
 * scored row) — same rule as Top Picks. */
function fitValue(row: InboxRow): number | null | undefined {
  const fit = row.fit;
  if (typeof fit === "number" && fit >= 0) return fit;
  return row.score;
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-2">
      <h3 className="text-muted-foreground flex items-center gap-1.5 text-xs font-semibold tracking-wide uppercase">
        {icon}
        {title}
      </h3>
      {children}
    </section>
  );
}

function FitWhy({
  fit,
  why,
}: {
  fit: number | null | undefined;
  why: string | undefined;
}) {
  const text = (why ?? "").trim();
  return (
    <Section title="Why it matched">
      <div className="flex items-start gap-2.5">
        <ScoreChip value={fit} />
        <p className="text-foreground/90 flex-1 text-sm leading-relaxed">
          {text || (
            <span className="text-muted-foreground">
              No AI rationale yet — rank this batch with AI to get one.
            </span>
          )}
        </p>
      </div>
    </Section>
  );
}

/** The score breakdown — a dict of {label: contribution/note}. Numeric values get
 * a mono numeral; string notes render as plain lines. Never a raw gray: labels are
 * muted, values are ink. */
function ScoreBreakdown({
  notes,
}: {
  notes: Record<string, unknown> | undefined;
}) {
  const entries = Object.entries(notes ?? {}).filter(
    ([, v]) => !isEmptyNote(v),
  );
  if (entries.length === 0) return null;
  return (
    <Section title="Score breakdown">
      <ul className="space-y-1.5">
        {entries.map(([label, value]) => (
          <li
            key={label}
            className="flex items-baseline justify-between gap-3 text-sm"
          >
            <span className="text-muted-foreground capitalize">
              {label.replace(/_/g, " ")}
            </span>
            <span
              className={cn(
                "text-foreground max-w-[60%] text-right",
                typeof value === "number" && "zg-num tabular-nums",
              )}
            >
              {formatNoteValue(value)}
            </span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

/** Is a score-note value "nothing to show" (null / blank / empty list or object)?
 * The engine's score_breakdown carries empty ``components`` / ``penalties`` arrays
 * and null ``board_count`` / ``size_adj`` for a plainly-scored row — those would
 * otherwise render as blank lines. */
function isEmptyNote(v: unknown): boolean {
  if (v === null || v === undefined || v === "") return true;
  if (Array.isArray(v)) return v.length === 0;
  if (typeof v === "object") return Object.keys(v as object).length === 0;
  return false;
}

function formatNoteValue(value: unknown): string {
  if (typeof value === "number") {
    return value > 0 ? `+${value}` : String(value);
  }
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (Array.isArray(value)) {
    return value
      .map((v) =>
        typeof v === "object" && v !== null ? JSON.stringify(v) : String(v),
      )
      .join(", ");
  }
  if (typeof value === "object" && value !== null) return JSON.stringify(value);
  return String(value);
}

/** The ghost/staleness warning banner — shown only when the ghost checker flagged
 * a concern (level 'stale' or 'warn'). Amber for stale, subtle for a softer warn. */
function GhostBanner({
  ghost,
}: {
  ghost: Record<string, unknown> | undefined;
}) {
  const level = String(ghost?.level ?? "").toLowerCase();
  if (level !== "stale" && level !== "warn") return null;
  const reason =
    (typeof ghost?.reason === "string" && ghost.reason) ||
    (level === "stale"
      ? "This posting looks stale — it may no longer be open."
      : "This posting may be older than it appears.");
  const isStale = level === "stale";
  return (
    <div
      className={cn(
        "flex items-start gap-2.5 rounded-md border px-3 py-2.5 text-sm leading-relaxed",
        isStale
          ? "border-[var(--zg-warn)]/40 bg-[var(--zg-warn)]/10 text-[var(--zg-warn)]"
          : "border-border bg-secondary/50 text-muted-foreground",
      )}
    >
      <Ghost className="mt-0.5 size-4 shrink-0" />
      <span>{reason}</span>
    </div>
  );
}

/** The ATS keyword hint — how the job's requirements line up with the user's
 * skill terms. We render the server's pre-formatted `lines`, plus a compact
 * matched/missing summary when present. */
function AtsHint({
  ats,
}: {
  ats:
    | {
        ats: string;
        matched: string[];
        missing: string[];
        have: number;
        lines: string[];
      }
    | undefined;
}) {
  if (!ats) return null;
  const lines = ats.lines ?? [];
  const hasContent =
    lines.length > 0 || ats.matched.length > 0 || ats.missing.length > 0;
  if (!hasContent) return null;
  return (
    <Section
      title="ATS keyword hint"
      icon={<FileSearch className="size-3.5" />}
    >
      {lines.length > 0 && (
        <ul className="space-y-1">
          {lines.map((ln, i) => (
            <li key={i} className="text-foreground/90 text-sm leading-relaxed">
              {ln}
            </li>
          ))}
        </ul>
      )}
      {(ats.matched.length > 0 || ats.missing.length > 0) && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {ats.matched.slice(0, 12).map((k) => (
            <KeywordChip key={`m-${k}`} tone="match">
              {k}
            </KeywordChip>
          ))}
          {ats.missing.slice(0, 12).map((k) => (
            <KeywordChip key={`x-${k}`} tone="miss">
              {k}
            </KeywordChip>
          ))}
        </div>
      )}
    </Section>
  );
}

function KeywordChip({
  tone,
  children,
}: {
  tone: "match" | "miss";
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[var(--radius-chip)] border px-1.5 py-0.5 text-xs",
        tone === "match"
          ? "border-[var(--zg-success)]/40 bg-[var(--zg-success)]/10 text-[var(--zg-success)]"
          : "border-border text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}

function DescriptionPreview({ text }: { text: string | undefined }) {
  const preview = (text ?? "").trim();
  if (!preview) return null;
  return (
    <Section title="Preview">
      <p className="text-muted-foreground max-h-56 overflow-y-auto text-sm leading-relaxed">
        {preview}
        {preview.length >= 500 && "…"}
      </p>
    </Section>
  );
}
