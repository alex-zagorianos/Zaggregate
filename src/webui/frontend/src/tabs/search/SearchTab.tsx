import * as React from "react";
import { toast } from "sonner";
import {
  Search as SearchIcon,
  Loader2,
  CheckCircle2,
  XCircle,
  ExternalLink,
  Inbox,
  Save,
  Building2,
  ListPlus,
  MapPin,
  Sparkles,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/api/queries";
import {
  endpoints,
  ApiError,
  type SearchRow,
  type SearchResult,
  type SearchArgs,
  type JobStatus,
  type RunConflictBody,
} from "@/api/client";
import { useRegisterCommands, type AppCommand } from "@/lib/app-commands";
import { ScoreChip } from "@/components/score-chip";
import { EmptyState } from "@/components/states";
import { ShortcutHint } from "@/components/kbd";
import { TriageActions } from "@/components/row-actions";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

import { useCompaniesFlows } from "@/tabs/companies/CompaniesFlows";
import { AiSetupDialog } from "@/components/ai-setup-dialog";
import { SearchRunConsole } from "./SearchRunConsole";
import { SourceHealthStrip } from "./SourceHealthStrip";

/* Search — run a multi-source job search without leaving the app, score every
 * result 0–100, then Track / Dismiss / Add-to-Inbox each row.
 *
 * The form (keywords comma text, location, min-salary, Save + Hide-tracked toggles)
 * mirrors the tk SearchTab's fields; "Search now" starts an EXCLUSIVE engine job and
 * streams per-source progress into the SearchRunConsole drawer. On finish the drawer
 * hands back {rows, health}: the results table renders (score chip, role, company,
 * location, salary, source; seen rows muted + tagged) and a source-health strip
 * summarizes the run. Triage is keyboard-first (t/d/o on the focused row).
 *
 * INCLUSION OVER PRECISION: nothing is hidden — "Hide tracked/dismissed" only mutes
 * already-seen rows (they still show, tagged), and dismiss is an explicit action. */

export function SearchTab() {
  const qc = useQueryClient();
  const companies = useCompaniesFlows();

  // ── form state ────────────────────────────────────────────────────────────
  const [keywords, setKeywords] = React.useState("");
  const [location, setLocation] = React.useState("");
  const [minSalary, setMinSalary] = React.useState("");
  const [save, setSave] = React.useState(false);
  const [hideTracked, setHideTracked] = React.useState(true);

  // No dedicated config GET exists in Phase 4, so the form starts blank and the
  // /search route falls back to the project config's keywords/location/salary when
  // a field is empty (server-side, in start_search) — behavior stays correct either
  // way; a future config-prefill can populate these fields.

  // Discover handoff (EXPERIMENTAL, S36c): a recommendation card's "Search now"
  // stashes its keywords in sessionStorage; consume-and-clear on mount so a
  // refresh doesn't resurrect them.
  React.useEffect(() => {
    try {
      const prefill = sessionStorage.getItem("zg-search-prefill");
      if (prefill) {
        sessionStorage.removeItem("zg-search-prefill");
        setKeywords(prefill);
      }
    } catch {
      /* sessionStorage unavailable — nothing to prefill */
    }
  }, []);

  // ── run + console ───────────────────────────────────────────────────────────
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [consoleOpen, setConsoleOpen] = React.useState(false);
  const [running, setRunning] = React.useState(false);
  const [result, setResult] = React.useState<SearchResult | null>(null);
  const [startError, setStartError] = React.useState<string | null>(null);

  // "Set up with AI" dialog (S40): the combined config+seeds express lane, but
  // autorun:false — applying lands the config, and its applied pane offers a
  // "Run search now" button that fires the SAME start mutation as the form.
  const [aiSetupOpen, setAiSetupOpen] = React.useState(false);

  const rows = result?.rows ?? [];
  const health = result?.health ?? [];

  const startSearch = React.useCallback(() => {
    setStartError(null);
    const kw = keywords.trim();
    // Send keywords as a comma string (server splits); blank => server falls back
    // to the project config keywords. Location/salary likewise optional.
    const args: SearchArgs = {
      keywords: kw || undefined,
      location: location.trim() || undefined,
      min_salary: minSalary.trim() ? Number(minSalary) : undefined,
      save,
      hide_tracked: hideTracked,
    };
    setRunning(true);
    setResult(null);
    endpoints
      .startSearch(args)
      .then((r) => {
        setJobId(r.job_id);
        setConsoleOpen(true);
        if (save)
          toast.success("Defaults saved", {
            description:
              "Keywords, location, and salary saved for this project.",
          });
      })
      .catch((e) => {
        setRunning(false);
        if (e instanceof ApiError && e.status === 409) {
          const body = e.body as RunConflictBody | null;
          if (body?.job_id) {
            setJobId(body.job_id);
            setConsoleOpen(true);
            setRunning(true);
          }
          toast("Already running", {
            description: e.message || "A run is already in progress.",
          });
        } else if (e instanceof ApiError && e.status === 400) {
          setStartError(e.message);
          toast.error("Nothing to search", { description: e.message });
        } else {
          toast.error("Couldn't start the search", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          });
        }
      });
  }, [keywords, location, minSalary, save, hideTracked]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!running) startSearch();
  };

  const onResult = React.useCallback((res: SearchResult) => {
    setResult(res);
    // A search may have written to the inbox indirectly (no) — but Track/Add
    // below will; nothing to invalidate here beyond letting the tab render.
  }, []);

  const onTerminal = React.useCallback((_status: JobStatus) => {
    setRunning(false);
  }, []);

  // ── result mutations ────────────────────────────────────────────────────────
  // Optimistically mark a row as removed from the local result set (track/dismiss
  // both drop it), keeping the table responsive without a refetch (the search
  // result isn't a cached query — it's local state).
  const dropRow = React.useCallback((url: string) => {
    setResult((prev) =>
      prev ? { ...prev, rows: prev.rows.filter((r) => r.url !== url) } : prev,
    );
  }, []);

  const onTrack = React.useCallback(
    (row: SearchRow) => {
      endpoints
        .trackSearchRow(row)
        .then((r) => {
          if (r.added > 0) {
            toast.success("Tracked", {
              description: `${row.title} · ${row.company} moved to your tracker.`,
            });
            dropRow(row.url);
            qc.invalidateQueries({ queryKey: queryKeys.applicationsAll });
            qc.invalidateQueries({ queryKey: queryKeys.queue });
          } else {
            toast("Already tracked", {
              description: "This job is already in your tracker.",
            });
            dropRow(row.url);
          }
        })
        .catch((e) =>
          toast.error("Couldn't track", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          }),
        );
    },
    [dropRow, qc],
  );

  const onDismiss = React.useCallback(
    (row: SearchRow) => {
      endpoints
        .dismissSearchUrl(row.url)
        .then(() => {
          toast("Dismissed", {
            description: `${row.title} · ${row.company} hidden from future searches.`,
          });
          dropRow(row.url);
        })
        .catch((e) =>
          toast.error("Couldn't dismiss", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          }),
        );
    },
    [dropRow],
  );

  const onOpen = React.useCallback((row: SearchRow) => {
    if (row.url) window.open(String(row.url), "_blank", "noopener,noreferrer");
  }, []);

  // ── Add all to Inbox ────────────────────────────────────────────────────────
  const [confirmAddAll, setConfirmAddAll] = React.useState(false);
  const [addingAll, setAddingAll] = React.useState(false);
  const onAddAll = React.useCallback(() => {
    if (rows.length === 0) return;
    setAddingAll(true);
    endpoints
      .addAllToInbox(rows)
      .then((r) => {
        toast.success("Added to Inbox", {
          description: `${r.added} job${r.added === 1 ? "" : "s"} ready to triage.`,
        });
        qc.invalidateQueries({ queryKey: queryKeys.inboxAll });
        qc.invalidateQueries({ queryKey: queryKeys.topPicksAll });
      })
      .catch((e) =>
        toast.error("Couldn't add to Inbox", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
      )
      .finally(() => setAddingAll(false));
  }, [rows, qc]);

  // ── palette commands ────────────────────────────────────────────────────────
  const paletteCommands = React.useMemo<AppCommand[]>(
    () => [
      {
        id: "run-search",
        label: "Search for jobs now",
        icon: SearchIcon,
        run: () => {
          if (!running) startSearch();
        },
      },
    ],
    [running, startSearch],
  );
  useRegisterCommands("search", paletteCommands);

  return (
    <section aria-labelledby="search-heading" className="flex h-full flex-col">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1
            id="search-heading"
            className="zg-serif text-foreground flex items-center gap-2.5 text-2xl font-semibold tracking-tight"
          >
            <SearchIcon className="text-primary size-6" strokeWidth={2} />
            Search
          </h1>
          <p className="text-muted-foreground max-w-xl text-sm leading-relaxed">
            <ShortcutHint
              lead="Search every board at once. Each result is scored 0–100 for fit —"
              actions={[
                { key: "t", label: "track" },
                { key: "d", label: "dismiss" },
                { key: "o", label: "open" },
              ]}
              tail="on the focused row."
            />
          </p>
        </div>

        {/* Company-list tools — the tk Search-tab entry points for growing the
            employer registry the daily run scrapes. Plus the AI express-lane setup
            (S40): configure roles/location/salary + seed companies from one paste. */}
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={() => setAiSetupOpen(true)}>
            <Sparkles className="size-3.5" />
            Set up with AI
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => companies.open("add")}
          >
            <Building2 className="size-3.5" />
            Add companies
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => companies.open("build")}
          >
            <ListPlus className="size-3.5" />
            Build my list
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => companies.open("seed")}
          >
            <MapPin className="size-3.5" />
            Seed my area
          </Button>
        </div>
      </div>

      {/* Form card */}
      <form
        onSubmit={onSubmit}
        className="border-border bg-card mt-5 rounded-lg border p-4"
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-12">
          <div className="space-y-1.5 sm:col-span-6">
            <Label
              htmlFor="search-keywords"
              className="text-muted-foreground text-xs"
            >
              Keywords <span className="opacity-60">(comma-separated)</span>
            </Label>
            <Input
              id="search-keywords"
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder="e.g. mechanical engineer, design engineer"
              autoComplete="off"
            />
          </div>
          <div className="space-y-1.5 sm:col-span-3">
            <Label
              htmlFor="search-location"
              className="text-muted-foreground text-xs"
            >
              Location
            </Label>
            <Input
              id="search-location"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="City, ST or remote"
              autoComplete="off"
            />
          </div>
          <div className="space-y-1.5 sm:col-span-3">
            <Label
              htmlFor="search-salary"
              className="text-muted-foreground text-xs"
            >
              Min salary $
            </Label>
            <Input
              id="search-salary"
              value={minSalary}
              onChange={(e) =>
                setMinSalary(e.target.value.replace(/[^\d]/g, ""))
              }
              placeholder="optional"
              inputMode="numeric"
              className="zg-num"
            />
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2">
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={hideTracked}
              onChange={(e) => setHideTracked(e.target.checked)}
              className="accent-[var(--zg-accent)]"
            />
            <span className="text-foreground">Hide tracked / dismissed</span>
          </label>
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={save}
              onChange={(e) => setSave(e.target.checked)}
              className="accent-[var(--zg-accent)]"
            />
            <span className="text-foreground inline-flex items-center gap-1">
              <Save className="size-3.5 opacity-70" />
              Save as project defaults
            </span>
          </label>
          <div className="ml-auto">
            <Button type="submit" disabled={running}>
              {running ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <SearchIcon className="size-4" />
              )}
              Search now
            </Button>
          </div>
        </div>

        {startError && (
          <p className="text-destructive mt-3 text-xs">{startError}</p>
        )}
      </form>

      {/* Health strip (after a finished run) */}
      {health.length > 0 && (
        <div className="mt-4">
          <SourceHealthStrip health={health} />
        </div>
      )}

      {/* Results */}
      <div className="mt-4 min-h-0 flex-1">
        {running && rows.length === 0 ? (
          <RunningPlaceholder />
        ) : rows.length > 0 ? (
          <>
            <div className="mb-3 flex items-center justify-between gap-2">
              <span className="text-muted-foreground zg-num text-xs">
                {rows.length} result{rows.length === 1 ? "" : "s"}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setConfirmAddAll(true)}
                disabled={addingAll}
              >
                {addingAll ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Inbox className="size-3.5" />
                )}
                Add all to Inbox
              </Button>
            </div>
            <ResultsTable
              rows={rows}
              onTrack={onTrack}
              onDismiss={onDismiss}
              onOpen={onOpen}
            />
          </>
        ) : result ? (
          <EmptyState
            icon={SearchIcon}
            title="No results"
            message="Nothing came back for those keywords and location. Try broader keywords, a different location, or connect more sources in Settings."
          />
        ) : (
          <SearchEmpty />
        )}
      </div>

      {/* Set-up-with-AI express lane (S40): combined config+seeds, autorun:false.
          The applied pane offers "Run search now" which closes the dialog and fires
          the SAME start mutation the form uses. */}
      <AiSetupDialog
        open={aiSetupOpen}
        onOpenChange={setAiSetupOpen}
        promptKind="full"
        autorun={false}
        appliedExtra={() => (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setAiSetupOpen(false);
              if (!running) startSearch();
            }}
          >
            <SearchIcon className="size-3.5" />
            Run search now
          </Button>
        )}
      />

      {/* Streaming console */}
      <SearchRunConsole
        jobId={jobId}
        open={consoleOpen}
        onOpenChange={setConsoleOpen}
        onResult={onResult}
        onTerminal={onTerminal}
      />

      <ConfirmDialog
        open={confirmAddAll}
        onOpenChange={setConfirmAddAll}
        title="Add all results to your Inbox?"
        description={`${rows.length} job${rows.length === 1 ? "" : "s"} will be added to your Inbox for triage. Duplicates and per-company caps are handled automatically.`}
        confirmLabel="Add all"
        cancelLabel="Cancel"
        onConfirm={onAddAll}
      />
    </section>
  );
}

// ── results table ───────────────────────────────────────────────────────────

function ResultsTable({
  rows,
  onTrack,
  onDismiss,
  onOpen,
}: {
  rows: SearchRow[];
  onTrack: (r: SearchRow) => void;
  onDismiss: (r: SearchRow) => void;
  onOpen: (r: SearchRow) => void;
}) {
  const [focused, setFocused] = React.useState(0);
  const rowRefs = React.useRef<(HTMLTableRowElement | null)[]>([]);

  React.useEffect(() => {
    if (focused > rows.length - 1) setFocused(Math.max(0, rows.length - 1));
  }, [rows.length, focused]);

  const focusRow = (i: number) => {
    const clamped = Math.max(0, Math.min(rows.length - 1, i));
    setFocused(clamped);
    rowRefs.current[clamped]?.focus();
  };

  const onRowKeyDown = (e: React.KeyboardEvent, row: SearchRow, i: number) => {
    switch (e.key.toLowerCase()) {
      case "t":
        e.preventDefault();
        onTrack(row);
        break;
      case "d":
        e.preventDefault();
        onDismiss(row);
        break;
      case "o":
        e.preventDefault();
        onOpen(row);
        break;
      case "arrowdown":
        e.preventDefault();
        focusRow(i + 1);
        break;
      case "arrowup":
        e.preventDefault();
        focusRow(i - 1);
        break;
      default:
        break;
    }
  };

  return (
    <div className="border-border bg-card overflow-hidden rounded-lg border">
      <div className="relative w-full overflow-x-auto">
        <table className="w-full caption-bottom text-sm">
          <thead className="[&_tr]:border-b">
            <tr className="border-border/70 border-b">
              <Th className="w-16 text-center">Fit</Th>
              <Th className="min-w-[15rem]">Role</Th>
              <Th className="hidden md:table-cell">Location</Th>
              <Th className="zg-num hidden text-right lg:table-cell">Salary</Th>
              <Th className="hidden sm:table-cell">Source</Th>
              <Th className="w-[8.5rem] text-right">Actions</Th>
            </tr>
          </thead>
          <tbody className="[&_tr:last-child]:border-0">
            {rows.map((row, i) => {
              const seen = Boolean(row.seen);
              return (
                <tr
                  key={`${row.url}-${i}`}
                  ref={(el) => {
                    rowRefs.current[i] = el;
                  }}
                  tabIndex={i === focused ? 0 : -1}
                  onFocus={() => setFocused(i)}
                  onKeyDown={(e) => onRowKeyDown(e, row, i)}
                  aria-label={`${row.title} at ${row.company}`}
                  className={cn(
                    "group border-border/70 hover:bg-secondary/45 border-b outline-none transition-colors",
                    "focus-visible:bg-secondary/50 focus-visible:ring-ring/40 focus-visible:ring-2 focus-visible:ring-inset",
                    seen && "opacity-55",
                  )}
                >
                  <td className="px-3 py-2.5 text-center align-middle">
                    <ScoreChip value={scoreValue(row)} />
                  </td>
                  <td className="px-3 py-2.5 align-middle">
                    <div className="flex min-w-0 flex-col gap-0.5">
                      <span className="text-foreground flex items-center gap-2 truncate leading-snug font-medium">
                        {row.title || "Untitled role"}
                        {seen && (
                          <span className="border-border text-muted-foreground shrink-0 rounded-[var(--radius-chip)] border px-1 py-0.5 text-[0.65rem] font-medium">
                            already in inbox
                          </span>
                        )}
                      </span>
                      <span className="text-muted-foreground truncate text-xs">
                        {row.company || "Unknown company"}
                      </span>
                    </div>
                  </td>
                  <td className="text-muted-foreground hidden px-3 py-2.5 align-middle text-sm md:table-cell">
                    <span className="truncate">{row.location || "—"}</span>
                  </td>
                  <td className="zg-num text-muted-foreground hidden px-3 py-2.5 text-right align-middle text-xs lg:table-cell">
                    {row.salary || "—"}
                  </td>
                  <td className="text-muted-foreground hidden px-3 py-2.5 align-middle text-xs capitalize sm:table-cell">
                    {row.source_api || "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right align-middle">
                    <RowActions
                      row={row}
                      onTrack={onTrack}
                      onDismiss={onDismiss}
                      onOpen={onOpen}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** The base match score for the chip; -1/absent renders as the muted "—" pill. */
function scoreValue(row: SearchRow): number | null | undefined {
  const s = row.score;
  if (typeof s === "number" && s >= 0) return s;
  return null;
}

function Th({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <th
      className={cn(
        "text-muted-foreground h-10 px-3 text-left align-middle text-xs font-semibold tracking-wide whitespace-nowrap uppercase",
        className,
      )}
    >
      {children}
    </th>
  );
}

function RowActions({
  row,
  onTrack,
  onDismiss,
  onOpen,
}: {
  row: SearchRow;
  onTrack: (r: SearchRow) => void;
  onDismiss: (r: SearchRow) => void;
  onOpen: (r: SearchRow) => void;
}) {
  return (
    <TriageActions
      actions={[
        {
          key: "track",
          label: "Track (t)",
          onClick: () => onTrack(row),
          icon: <CheckCircle2 className="size-4" />,
          tone: "success",
        },
        {
          key: "dismiss",
          label: "Dismiss (d)",
          onClick: () => onDismiss(row),
          icon: <XCircle className="size-4" />,
          tone: "danger",
        },
        {
          key: "open",
          label: "Open (o)",
          onClick: () => onOpen(row),
          icon: <ExternalLink className="size-4" />,
          tone: "muted",
          disabled: !row.url,
        },
      ]}
    />
  );
}

function RunningPlaceholder() {
  return (
    <div className="border-border bg-card flex min-h-[40vh] flex-col items-center justify-center rounded-lg border px-6 text-center">
      <Loader2 className="text-primary/70 mb-4 size-8 animate-spin" />
      <p className="zg-serif text-foreground text-lg font-medium">Searching…</p>
      <p className="text-muted-foreground mt-1.5 max-w-sm text-sm leading-relaxed">
        Querying every connected source. Watch the progress below — results land
        here scored and ready to triage.
      </p>
    </div>
  );
}

function SearchEmpty() {
  return (
    <EmptyState
      icon={SearchIcon}
      title="Search for jobs"
      message="Enter keywords and a location above, then Search now. Every board runs at once and each result is scored for fit — track the good ones, add the batch to your Inbox, or dismiss the rest."
    />
  );
}
