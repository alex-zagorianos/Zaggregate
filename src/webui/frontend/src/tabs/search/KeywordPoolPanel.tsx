import * as React from "react";
import { toast } from "sonner";
import {
  Search as SearchIcon,
  Sparkles,
  ChevronDown,
  Loader2,
  History,
  Radar,
  TriangleAlert,
} from "lucide-react";

import { ApiError, type DiscoveryPoolRow } from "@/api/client";
import {
  useDiscoveryPool,
  useDiscoveryTypeahead,
  useProposeMutation,
  useProbeMutation,
  useMineMutation,
  useLevelsMutation,
  useActivateKeywordMutation,
  useDeactivateKeywordMutation,
} from "@/api/queries";
import { LEVEL_OPTIONS } from "@/lib/wizard-steps";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useQueryGuard } from "@/components/states";
import { cn } from "@/lib/utils";

/* KeywordPoolPanel — the one web surface for Search Discovery (search-discovery
 * plan §4.4): turn a free-typed field into a rich, reviewable keyword set, with
 * or without AI. Shared verbatim by SearchTab (a collapsible power tool tucked
 * under the search form) and the onboarding RolesStep (the default
 * keyword-picking view, always open).
 *
 * Layout: a field box (with typeahead), two action buttons ("From my résumé /
 * history" -> corpus-mine; "Check current openings" -> a small batch of live
 * yield probes) + an experience-level select, then three chip sections bucketed
 * by the pool row's TIER (never by status — a term keeps its section once
 * assigned, its checkbox alone tracks active/not):
 *   - "Searching now"  = tier "core"        (the primary/best-match candidates)
 *   - "More like this" = tier "adjacent"    (cross-occupation relatedness)
 *   - "Worth a look"   = tier "exploratory" (supplemental / longer-shot)
 *
 * UX rules enforced throughout: no SOC codes, no "probe"/"yield"/"tier" jargon
 * in any rendered string (see brain/search-discovery-plan.md §4.2's "fatal-flaw
 * fix (jargon)") — copy is "~N openings nearby" / "hasn't found much lately".
 * INCLUSION OVER PRECISION: a chip is never hidden or removed for a zero/low
 * count or a "low activity" flag — the low-activity nudge is a dismissible
 * hint, and dismissing only hides the NUDGE, never the chip or its status. */

export interface KeywordPoolPanelProps {
  /** Seeds the field box once on mount (e.g. SearchTab's typed keywords, or the
   * wizard's already-chosen industry) and fires an initial lookup if non-blank.
   * Purely a first-paint convenience — the user can always retype the field. */
  initialField?: string;
  /** Optional résumé text, passed through to /discovery/propose so a blank
   * field can resolve from it. NOT used to prefill the field box itself (never
   * a silent default, search-discovery-plan.md §7) — only the explicit "From my
   * résumé / history" button acts on the user's own data. */
  resumeText?: string;
  /** Called whenever the pool's ACTIVE ("searching now") term set changes, as a
   * comma-joined string of every currently-active term across all tiers. The
   * mutations already persist to cfg['keywords'] server-side regardless of
   * whether the caller wires this — it's a convenience so an embedding view
   * (SearchTab's keyword box, the wizard's roles box) can mirror the pool's
   * choices into its own field. Use `mergeTermsCsv` to fold it in without
   * clobbering anything the user already typed by hand. */
  onActiveTermsChange?: (csv: string) => void;
  /** Called with the free-typed field text whenever a lookup is submitted
   * (Enter, the search button, or picking a typeahead hit) — lets the wizard's
   * Roles step mirror it into `answers.industry` (any free text resolves fine
   * server-side; industry_profile.resolve() is not limited to a fixed list). */
  onFieldChange?: (field: string) => void;
  /** Render as an always-open section with no collapse chrome — the onboarding
   * RolesStep's usage (this IS the primary keyword-picking UI there). Default
   * false renders a collapsible header, matching SearchTab's "optional power
   * tool tucked under the search form" framing. */
  alwaysOpen?: boolean;
  className?: string;
}

export function KeywordPoolPanel({
  initialField,
  resumeText,
  onActiveTermsChange,
  onFieldChange,
  alwaysOpen = false,
  className,
}: KeywordPoolPanelProps) {
  const [expanded, setExpanded] = React.useState(true);
  const [field, setField] = React.useState(initialField ?? "");
  const [level, setLevel] = React.useState("");
  const [pendingTerms, setPendingTerms] = React.useState<Set<string>>(
    new Set(),
  );
  const [dismissedNudges, setDismissedNudges] = React.useState<Set<string>>(
    new Set(),
  );
  const [probesRemaining, setProbesRemaining] = React.useState<number | null>(
    null,
  );

  const poolQuery = useDiscoveryPool();
  const proposeMut = useProposeMutation();
  const probeMut = useProbeMutation();
  const mineMut = useMineMutation();
  const levelsMut = useLevelsMutation();
  const activateMut = useActivateKeywordMutation();
  const deactivateMut = useDeactivateKeywordMutation();

  const markPending = React.useCallback((term: string, on: boolean) => {
    setPendingTerms((prev) => {
      const next = new Set(prev);
      if (on) next.add(term);
      else next.delete(term);
      return next;
    });
  }, []);

  const submitField = React.useCallback(
    (value: string) => {
      const v = value.trim();
      if (!v) return;
      setField(v);
      onFieldChange?.(v);
      proposeMut.mutate(
        { field: v, resume: resumeText },
        {
          onError: (e) =>
            toast.error("Couldn't look up keywords", {
              description:
                e instanceof ApiError ? e.message : "Please try again.",
            }),
        },
      );
    },
    [proposeMut, resumeText, onFieldChange],
  );

  // Seed once from the initial field, and peek the probe budget for free (an
  // empty terms list never touches the network or the daily counter — see
  // discovery.py's probe route). Both fire exactly once on mount.
  const seededRef = React.useRef(false);
  React.useEffect(() => {
    if (seededRef.current) return;
    seededRef.current = true;
    const seed = (initialField || "").trim();
    if (seed) submitField(seed);
    probeMut.mutate(
      { terms: [] },
      { onSuccess: (r) => setProbesRemaining(r.probes_remaining_today) },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pool = poolQuery.data?.pool ?? [];
  const lowActivity = poolQuery.data?.low_activity ?? [];
  const buckets = React.useMemo(() => bucketPoolByTier(pool), [pool]);
  const activeTerms = React.useMemo(
    () => pool.filter((r) => r.status === "active").map((r) => r.term),
    [pool],
  );
  const visibleTerms = React.useMemo(
    () =>
      Array.from(
        new Set(
          [...buckets.core, ...buckets.adjacent, ...buckets.exploratory].map(
            (r) => r.term,
          ),
        ),
      ),
    [buckets],
  );
  const visibleNudges = lowActivity.filter((n) => !dismissedNudges.has(n.term));

  // Mirror the active set into the embedding view (if it's listening), merging
  // on the caller's side so nothing the user typed by hand gets clobbered.
  const activeCsv = React.useMemo(() => activeTerms.join(", "), [activeTerms]);
  const lastSentRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!onActiveTermsChange) return;
    if (lastSentRef.current === activeCsv) return;
    lastSentRef.current = activeCsv;
    if (!activeCsv) return; // nothing to merge in yet
    onActiveTermsChange(activeCsv);
  }, [activeCsv, onActiveTermsChange]);

  const toggleChip = React.useCallback(
    (row: DiscoveryPoolRow) => {
      const goingActive = row.status !== "active";
      markPending(row.term, true);
      const onSettled = () => markPending(row.term, false);
      if (goingActive) {
        activateMut.mutate(
          { term: row.term, tier: row.tier, source: row.source },
          {
            onSettled,
            onError: (e) =>
              toast.error("Couldn't turn that on", {
                description:
                  e instanceof ApiError ? e.message : "Please try again.",
              }),
          },
        );
      } else {
        deactivateMut.mutate(row.term, {
          onSettled,
          onError: (e) =>
            toast.error("Couldn't turn that off", {
              description:
                e instanceof ApiError ? e.message : "Please try again.",
            }),
        });
      }
    },
    [activateMut, deactivateMut, markPending],
  );

  const onMine = () => {
    mineMut.mutate(undefined, {
      onSuccess: (r) => {
        if (r.upserted > 0) {
          toast.success("Found some ideas", {
            description: `${r.upserted} new term${r.upserted === 1 ? "" : "s"} pulled from your inbox and applications.`,
          });
        } else {
          toast("Nothing new yet", {
            description:
              "Track a few more jobs and try again — we look at your own history.",
          });
        }
      },
      onError: (e) =>
        toast.error("Couldn't check your history", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
    });
  };

  const onCheckOpenings = () => {
    if (visibleTerms.length === 0) {
      toast("Nothing to check yet", {
        description: "Look up a field above to get some keyword ideas first.",
      });
      return;
    }
    probeMut.mutate(
      { terms: visibleTerms },
      {
        onSuccess: (r) => {
          setProbesRemaining(r.probes_remaining_today);
          const skippedNoKey = r.results.some(
            (x) => x.skipped && x.reason === "no_key",
          );
          const skippedBudget = r.results.filter(
            (x) => x.skipped && x.reason === "budget",
          ).length;
          if (skippedNoKey) {
            toast("No live counts available", {
              description:
                "Connect Adzuna in Settings to see real opening counts.",
            });
          } else if (skippedBudget > 0) {
            toast("Checked what today's limit allowed", {
              description: `${skippedBudget} term${skippedBudget === 1 ? "" : "s"} will check again tomorrow.`,
            });
          } else {
            toast.success("Openings checked", {
              description: "Counts updated on the chips below.",
            });
          }
        },
        onError: (e) =>
          toast.error("Couldn't check openings", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          }),
      },
    );
  };

  const onLevelChange = (v: string) => {
    setLevel(v);
    if (!v) return;
    levelsMut.mutate(
      { level: v, terms: activeTerms.length ? activeTerms : undefined },
      {
        onSuccess: (r) => {
          if (r.variants.length === 0) {
            toast("No phrasing changes for that level", {
              description:
                "Senior and manager titles search better as-is — nothing to add.",
            });
          } else {
            toast.success("Added some phrasing ideas", {
              description: `${r.variants.length} variant${r.variants.length === 1 ? "" : "s"} added to Worth a look.`,
            });
          }
        },
        onError: (e) =>
          toast.error("Couldn't generate variants", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          }),
      },
    );
  };

  const onNudgeTurnOff = (term: string) => {
    markPending(term, true);
    deactivateMut.mutate(term, {
      onSettled: () => markPending(term, false),
      onError: (e) =>
        toast.error("Couldn't turn that off", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
    });
  };

  const guard = useQueryGuard(poolQuery, {
    title: "Couldn't load your keyword pool",
    fallback: "Please try again.",
    loading: <PanelSkeleton />,
    errorClassName: "min-h-0 py-6",
  });

  const body = guard ?? (
    <>
      <FieldInputRow
        field={field}
        onFieldChange={setField}
        onSubmit={submitField}
        submitting={proposeMut.isPending}
      />

      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onMine}
          disabled={mineMut.isPending}
        >
          {mineMut.isPending ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <History className="size-3.5" />
          )}
          From my résumé / history
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onCheckOpenings}
          disabled={probeMut.isPending}
        >
          {probeMut.isPending ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Radar className="size-3.5" />
          )}
          Check current openings
        </Button>
        {probesRemaining !== null && (
          <span className="text-muted-foreground zg-num text-xs">
            {probesRemaining} check{probesRemaining === 1 ? "" : "s"} left today
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <Label htmlFor="kw-level" className="text-muted-foreground text-xs">
            Experience level
          </Label>
          <Select
            id="kw-level"
            value={level}
            onChange={(e) => onLevelChange(e.target.value)}
            className="h-8 w-auto min-w-[9.5rem]"
          >
            {LEVEL_OPTIONS.map((l) => (
              <option key={l || "none"} value={l}>
                {l || "Leave as-is"}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {visibleNudges.length > 0 && (
        <div className="space-y-2">
          {visibleNudges.map((n) => (
            <div
              key={n.term}
              className="border-border bg-secondary/30 flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-xs"
            >
              <TriangleAlert className="text-muted-foreground size-3.5 shrink-0" />
              <span className="text-foreground flex-1">
                <span className="font-medium">{n.term}</span> hasn&apos;t turned
                up much lately.
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs"
                disabled={pendingTerms.has(n.term)}
                onClick={() => onNudgeTurnOff(n.term)}
              >
                Turn off
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-muted-foreground h-7 px-2 text-xs"
                onClick={() =>
                  setDismissedNudges((prev) => new Set(prev).add(n.term))
                }
              >
                Keep it on
              </Button>
            </div>
          ))}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <ChipSection
          title="Searching now"
          rows={buckets.core}
          emptyHint="Type a field above to get started."
          pendingTerms={pendingTerms}
          onToggle={toggleChip}
        />
        <ChipSection
          title="More like this"
          rows={buckets.adjacent}
          emptyHint="Related titles will show up here."
          pendingTerms={pendingTerms}
          onToggle={toggleChip}
        />
        <ChipSection
          title="Worth a look"
          rows={buckets.exploratory}
          emptyHint="A few longer-shot ideas will show up here."
          pendingTerms={pendingTerms}
          onToggle={toggleChip}
        />
      </div>
    </>
  );

  return (
    <Card className={cn("border-border", className)}>
      <CardHeader
        className={cn(!alwaysOpen && "cursor-pointer select-none")}
        onClick={alwaysOpen ? undefined : () => setExpanded((e) => !e)}
      >
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Sparkles className="text-primary size-4" />
            <CardTitle className="text-base">Find keywords</CardTitle>
          </div>
          {!alwaysOpen && (
            <ChevronDown
              className={cn(
                "text-muted-foreground size-4 transition-transform",
                expanded && "rotate-180",
              )}
            />
          )}
        </div>
        <CardDescription>
          Type a field or job title — we&apos;ll suggest related keywords, no
          industry jargon required.
        </CardDescription>
      </CardHeader>

      {expanded && <CardContent className="space-y-5">{body}</CardContent>}
    </Card>
  );
}

// ── field input + typeahead ────────────────────────────────────────────────────

function FieldInputRow({
  field,
  onFieldChange,
  onSubmit,
  submitting,
}: {
  field: string;
  onFieldChange: (v: string) => void;
  onSubmit: (v: string) => void;
  submitting: boolean;
}) {
  const [debounced, setDebounced] = React.useState(field);
  const [open, setOpen] = React.useState(false);
  React.useEffect(() => {
    const t = setTimeout(() => setDebounced(field), 250);
    return () => clearTimeout(t);
  }, [field]);
  const typeahead = useDiscoveryTypeahead(debounced);
  const suggestions = typeahead.data?.suggestions ?? [];

  return (
    <div className="relative">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <SearchIcon className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
          <Input
            value={field}
            onChange={(e) => {
              onFieldChange(e.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 120)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                onSubmit(field);
                setOpen(false);
              } else if (e.key === "Escape") {
                setOpen(false);
              }
            }}
            placeholder="e.g. mechanic, mechanical engineer, welder…"
            aria-label="Field or job title"
            autoComplete="off"
            className="pl-8"
          />
          {open && suggestions.length > 0 && (
            <div className="bg-popover text-popover-foreground border-border absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-md border shadow-md">
              {suggestions.map((s) => (
                <button
                  key={`${s.kind}-${s.term}`}
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => {
                    onSubmit(s.term);
                    setOpen(false);
                  }}
                  className="hover:bg-secondary/60 flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm"
                >
                  <span className="truncate">{s.term}</span>
                  <span className="text-muted-foreground shrink-0 text-[0.65rem] uppercase">
                    {s.kind}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
        <Button
          type="button"
          size="icon"
          variant="outline"
          aria-label="Look up keywords"
          disabled={submitting || !field.trim()}
          onClick={() => onSubmit(field)}
        >
          {submitting ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <SearchIcon className="size-4" />
          )}
        </Button>
      </div>
    </div>
  );
}

// ── chip sections ───────────────────────────────────────────────────────────────

function ChipSection({
  title,
  rows,
  emptyHint,
  pendingTerms,
  onToggle,
}: {
  title: string;
  rows: DiscoveryPoolRow[];
  emptyHint: string;
  pendingTerms: Set<string>;
  onToggle: (row: DiscoveryPoolRow) => void;
}) {
  return (
    <div className="space-y-2">
      <h4 className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
        {title}
      </h4>
      {rows.length === 0 ? (
        <p className="text-muted-foreground text-xs italic">{emptyHint}</p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {rows.map((row) => (
            <Chip
              key={row.id}
              row={row}
              pending={pendingTerms.has(row.term)}
              onToggle={() => onToggle(row)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function Chip({
  row,
  pending,
  onToggle,
}: {
  row: DiscoveryPoolRow;
  pending: boolean;
  onToggle: () => void;
}) {
  const active = row.status === "active";
  const label = yieldCopy(row);
  return (
    <button
      type="button"
      role="switch"
      aria-checked={active}
      disabled={pending}
      onClick={onToggle}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[var(--radius-chip)] border px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-60",
        "focus-visible:ring-ring/50 outline-none focus-visible:ring-2",
        active
          ? "border-primary/50 bg-primary/12 text-primary"
          : "border-border text-muted-foreground hover:text-foreground hover:border-ring/40",
      )}
    >
      {pending ? (
        <Loader2 className="size-3 animate-spin" />
      ) : (
        <span
          aria-hidden
          className={cn(
            "size-1.5 rounded-full",
            active ? "bg-primary" : "bg-muted-foreground/40",
          )}
        />
      )}
      {row.term}
      {label && (
        <span
          className={cn(
            "zg-num text-[0.7rem]",
            active ? "text-primary/80" : "text-muted-foreground",
          )}
        >
          {label}
        </span>
      )}
    </button>
  );
}

function PanelSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-9 w-full" />
      <div className="flex gap-2">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-8 w-44" />
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-3/4" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ── pure helpers (exported for unit tests — see KeywordPoolPanel.test.ts) ──────

/** The chip copy for a pool row's live-probed yield. Never shown until the term
 * has actually been probed (`yield_date` set) — a never-probed term shows no
 * annotation at all, rather than a misleading "0 openings". Matches the plan's
 * jargon-free copy exactly: "~N openings nearby" / "hasn't found much lately". */
export function yieldCopy(
  row: Pick<DiscoveryPoolRow, "yield_date" | "yield_count">,
): string | null {
  if (!row.yield_date) return null;
  if (row.yield_count && row.yield_count > 0) {
    return `~${row.yield_count} openings nearby`;
  }
  return "hasn't found much lately";
}

/** Bucket the full pool by tier for the three chip sections. `negative`-tier
 * rows (a valid tier no route in this panel ever populates) are dropped —
 * there's no section for them here. */
export function bucketPoolByTier(pool: DiscoveryPoolRow[]): {
  core: DiscoveryPoolRow[];
  adjacent: DiscoveryPoolRow[];
  exploratory: DiscoveryPoolRow[];
} {
  const core: DiscoveryPoolRow[] = [];
  const adjacent: DiscoveryPoolRow[] = [];
  const exploratory: DiscoveryPoolRow[] = [];
  for (const row of pool) {
    if (row.tier === "core") core.push(row);
    else if (row.tier === "adjacent") adjacent.push(row);
    else if (row.tier === "exploratory") exploratory.push(row);
  }
  return { core, adjacent, exploratory };
}

/** Union-merge a comma-list of newly-active terms into an existing comma-list
 * (e.g. SearchTab's keyword box, the wizard's roles box), case-insensitively
 * deduped, keeping the existing terms' order/casing and appending any
 * genuinely-new ones. One-directional by design: deactivating a term in the
 * panel does NOT remove it here — the embedding field is the user's own typed
 * content, and this never silently deletes anything from it. */
export function mergeTermsCsv(existing: string, incoming: string): string {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of `${existing},${incoming}`.split(",")) {
    const t = raw.trim();
    if (!t) continue;
    const key = t.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(t);
  }
  return out.join(", ");
}
