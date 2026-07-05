import { BarChart3, Users } from "lucide-react";

import { useInsights } from "@/api/queries";
import {
  ApiError,
  type InsightsFunnel,
  type InsightsSourceRow,
  type InsightsCadence,
} from "@/api/client";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

/* Insights — read-only channel conversion + application cadence (B6). Three
 * sections:
 *   1. Funnel row: big zg-num counts across tracked -> applied -> interview ->
 *      offer/accepted, with the conversion % between adjacent stages.
 *   2. "Where your interviews come from": per-source applied / interviews / rate,
 *      with an honest empty state before there's enough data.
 *   3. Cadence: a pure-CSS weekly bar chart + the steady-10-20/week guidance.
 * No mutations, no chart dependency. */

/** Format a 0..1 rate as a whole-percent string. */
function pct(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

export function InsightsTab() {
  const query = useInsights();

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return (
      <ErrorState
        title="Couldn't load your insights"
        message={
          query.error instanceof ApiError
            ? query.error.message
            : "The insights service didn't respond."
        }
        onRetry={() => query.refetch()}
      />
    );
  }

  const data = query.data;
  const funnel = data?.funnel;
  const bySource = data?.by_source ?? [];
  const cadence = data?.cadence;

  // Nothing tracked at all — the whole tab is empty until you track a job.
  if (!funnel || funnel.tracked === 0) {
    return (
      <EmptyState
        icon={BarChart3}
        title="No insights yet"
        message="Track a few applications and this fills in — you'll see where your interviews come from and how steady your pace is."
      />
    );
  }

  return (
    <section aria-labelledby="insights-heading" className="flex flex-col">
      <header className="mb-6">
        <h1
          id="insights-heading"
          className="zg-serif text-foreground flex items-center gap-2.5 text-2xl font-semibold tracking-tight"
        >
          <BarChart3 className="text-primary size-6" strokeWidth={2} />
          Insights
        </h1>
        <p className="text-muted-foreground mt-1 max-w-2xl text-sm leading-relaxed">
          How your applications convert, which channels land interviews, and
          whether your pace is steady — computed from the jobs you&apos;ve
          tracked. Read-only.
        </p>
      </header>

      <FunnelRow funnel={funnel} />
      <SourceTable rows={bySource} />
      {cadence && <CadenceChart cadence={cadence} />}
    </section>
  );
}

// ── Funnel row ──────────────────────────────────────────────────────────────

/** A stage tile (big number + label) with an optional conversion % arrow to its
 * right. Offer and Accepted share the last tile pair. */
function FunnelRow({ funnel }: { funnel: InsightsFunnel }) {
  // The success terminal is whichever of offer/accepted the user has reached; we
  // show both stages so the offer->accepted step is visible.
  const stages: { label: string; value: number; rate?: number }[] = [
    { label: "Tracked", value: funnel.tracked },
    { label: "Applied", value: funnel.applied, rate: funnel.applied_rate },
    {
      label: "Interview",
      value: funnel.interview,
      rate: funnel.interview_rate,
    },
    { label: "Offer", value: funnel.offer, rate: funnel.offer_rate },
    { label: "Accepted", value: funnel.accepted, rate: funnel.accepted_rate },
  ];

  return (
    <div>
      <div className="border-border/60 bg-card/50 flex flex-wrap items-stretch gap-x-2 gap-y-4 rounded-lg border p-5">
        {stages.map((s, i) => (
          <div key={s.label} className="flex items-center gap-2">
            {i > 0 && (
              <div className="flex flex-col items-center px-1 text-center">
                <span className="text-muted-foreground/60 text-lg leading-none">
                  →
                </span>
                <span className="zg-num text-muted-foreground mt-1 text-xs font-medium">
                  {pct(s.rate ?? 0)}
                </span>
              </div>
            )}
            <div className="min-w-[5.5rem] text-center">
              <div className="zg-num text-foreground text-3xl font-semibold tracking-tight tabular-nums">
                {s.value}
              </div>
              <div className="text-muted-foreground mt-1 text-xs font-medium tracking-wide uppercase">
                {s.label}
              </div>
            </div>
          </div>
        ))}
      </div>
      {funnel.ghosted > 0 && (
        <p className="text-muted-foreground mt-2 text-xs">
          <span className="zg-num tabular-nums">{funnel.ghosted}</span> ghosted
          — the employer went silent after you applied.
        </p>
      )}
    </div>
  );
}

// ── Source table ────────────────────────────────────────────────────────────

function SourceTable({ rows }: { rows: InsightsSourceRow[] }) {
  return (
    <div className="mt-8">
      <h2 className="zg-serif text-foreground mb-1 flex items-center gap-2 text-lg font-semibold">
        <Users className="text-primary size-4" strokeWidth={2} />
        Where your interviews come from
      </h2>
      <p className="text-muted-foreground mb-3 text-sm">
        Which sources actually convert applications into interviews.
      </p>
      {rows.length === 0 ? (
        <div className="border-border/60 rounded-lg border border-dashed p-8 text-center">
          <p className="text-muted-foreground text-sm">
            Track a few applications and this fills in.
          </p>
        </div>
      ) : (
        <div className="border-border/60 overflow-x-auto rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Source</TableHead>
                <TableHead className="text-right">Applied</TableHead>
                <TableHead className="text-right">Interviews</TableHead>
                <TableHead className="text-right">Rate</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.source}>
                  <TableCell className="font-medium capitalize">
                    {r.source}
                  </TableCell>
                  <TableCell className="zg-num text-right tabular-nums">
                    {r.applied}
                  </TableCell>
                  <TableCell className="zg-num text-right tabular-nums">
                    {r.interviews}
                  </TableCell>
                  <TableCell className="text-right">
                    <span className="zg-num tabular-nums">
                      {pct(r.interview_rate)}
                    </span>
                    {r.low_n && (
                      <span
                        className="text-muted-foreground ml-1.5 text-xs"
                        title="Fewer than 5 applications — the rate is still noisy."
                      >
                        (thin)
                      </span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}

// ── Cadence chart (pure CSS/divs — no chart dependency) ─────────────────────

function CadenceChart({ cadence }: { cadence: InsightsCadence }) {
  const max = Math.max(1, ...cadence.weeks.map((w) => w.count));
  return (
    <div className="mt-8">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="zg-serif text-foreground text-lg font-semibold">
          Your application cadence
        </h2>
        <div className="text-muted-foreground text-xs">
          <span className="zg-num tabular-nums">{cadence.streak}</span>-week
          streak · avg{" "}
          <span className="zg-num tabular-nums">{cadence.per_week_avg}</span>
          /week
        </div>
      </div>

      <div className="border-border/60 bg-card/50 rounded-lg border p-5">
        {/* Bar chart: one column per week, height ∝ count. Pure divs. */}
        <div
          className="flex h-40 items-end gap-1.5"
          role="img"
          aria-label={`Applications per week over the last ${cadence.weeks.length} weeks`}
        >
          {cadence.weeks.map((w) => {
            const heightPct = (w.count / max) * 100;
            const inBand =
              w.count >= cadence.target_min && w.count <= cadence.target_max;
            return (
              <div
                key={w.week_start}
                className="flex flex-1 flex-col items-center justify-end gap-1"
                title={`Week of ${w.week_start}: ${w.count} application${w.count === 1 ? "" : "s"}`}
              >
                <span className="zg-num text-muted-foreground text-[0.65rem] tabular-nums">
                  {w.count}
                </span>
                <div
                  className={[
                    "w-full rounded-t transition-[height]",
                    w.current
                      ? "bg-primary"
                      : inBand
                        ? "bg-primary/70"
                        : "bg-primary/35",
                  ].join(" ")}
                  style={{
                    height: `${Math.max(heightPct, w.count > 0 ? 6 : 2)}%`,
                  }}
                />
              </div>
            );
          })}
        </div>
        {/* Target band caption */}
        <p className="text-muted-foreground mt-4 text-sm leading-relaxed">
          A steady{" "}
          <span className="zg-num text-foreground font-medium tabular-nums">
            {cadence.target_min}–{cadence.target_max}
          </span>{" "}
          quality applications a week beats bursts — the data says consistency
          wins.
        </p>
      </div>
    </div>
  );
}
