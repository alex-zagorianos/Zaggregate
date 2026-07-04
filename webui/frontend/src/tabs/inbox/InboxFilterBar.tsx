import * as React from "react";
import { Search, X, SlidersHorizontal, Filter } from "lucide-react";

import {
  type InboxFilterState,
  type LocationMode,
  type SizeOption,
  type InboxOrder,
  LOCATION_MODES,
  SIZE_OPTIONS,
  activeFilterCount,
  isDefaultFilters,
  makeDefaultFilters,
} from "@/lib/inbox-filter-state";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuCheckboxItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

/* The Inbox filter bar. Every control is a VIEW filter (inclusion over precision):
 * changing one never deletes a job, only changes what's shown. The min-score is a
 * slider (0 = show everything), sources is a multi-select (empty = all), size and
 * location are selects, pay-floor / new / unscored / hide-stale are toggle chips,
 * and there's a debounced free-text search. An active-count chip + one-click Clear
 * live on the right, and the "N of M shown" line is rendered by the parent (it owns
 * the totals). */

const MIN_SCORE_STEP = 5;

export interface InboxFilterBarProps {
  state: InboxFilterState;
  onChange: (next: InboxFilterState) => void;
  /** The distinct source ids present in the current (unfiltered) rows. */
  availableSources: string[];
  /** The rendered "N of M" summary the parent computes. */
  summary: React.ReactNode;
  /** Debounced search value → parent (already 200ms-debounced here). */
  onSearchDebounced: (q: string) => void;
}

export function InboxFilterBar({
  state,
  onChange,
  availableSources,
  summary,
  onSearchDebounced,
}: InboxFilterBarProps) {
  const set = <K extends keyof InboxFilterState>(
    key: K,
    value: InboxFilterState[K],
  ) => onChange({ ...state, [key]: value });

  // Local (immediate) search text; debounced push to the parent so we don't refetch
  // on every keystroke (plan: debounced 200ms, hits ?q=).
  const [searchText, setSearchText] = React.useState(state.q);
  React.useEffect(() => setSearchText(state.q), [state.q]);
  React.useEffect(() => {
    const t = setTimeout(() => onSearchDebounced(searchText), 200);
    return () => clearTimeout(t);
  }, [searchText, onSearchDebounced]);

  const activeCount = activeFilterCount(state);
  const atDefault = isDefaultFilters(state);

  return (
    <div className="mt-5 space-y-3">
      {/* Row 1: search + primary selects + active-count/clear */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[13rem] flex-1 sm:max-w-xs">
          <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
          <Input
            type="search"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="Search title or company…"
            aria-label="Search the inbox"
            className="pl-8"
          />
          {searchText && (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => setSearchText("")}
              className="text-muted-foreground hover:text-foreground absolute top-1/2 right-2 -translate-y-1/2 rounded p-0.5"
            >
              <X className="size-3.5" />
            </button>
          )}
        </div>

        <SourceMenu
          selected={state.sources}
          available={availableSources}
          onChange={(sources) => set("sources", sources)}
        />

        <LabeledSelect
          label="Size"
          value={state.size}
          onChange={(v) => set("size", v as SizeOption)}
          options={SIZE_OPTIONS.map((s) => ({
            value: s,
            label: s === "All" ? "All sizes" : s === "?" ? "Unknown" : s,
          }))}
        />

        <LabeledSelect
          label="Location"
          value={state.locationMode}
          onChange={(v) => set("locationMode", v as LocationMode)}
          options={LOCATION_MODES.map((m) => ({ value: m, label: m }))}
        />

        <LabeledSelect
          label="Sort"
          value={state.order}
          onChange={(v) => set("order", v as InboxOrder)}
          options={[
            { value: "roundrobin", label: "Diverse" },
            { value: "score", label: "By score" },
          ]}
        />

        <div className="ml-auto flex items-center gap-2">
          {activeCount > 0 && (
            <span className="text-muted-foreground zg-num inline-flex items-center gap-1 text-xs">
              <Filter className="size-3.5" />
              {activeCount} active
            </span>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onChange(makeDefaultFilters())}
            disabled={atDefault}
            className="text-muted-foreground hover:text-foreground"
          >
            Clear
          </Button>
        </div>
      </div>

      {/* Row 2: min-score slider + toggle chips + summary */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5">
        <div className="flex items-center gap-2.5">
          <SlidersHorizontal className="text-muted-foreground size-4" />
          <label
            htmlFor="min-score"
            className="text-muted-foreground text-xs whitespace-nowrap"
          >
            Min score
          </label>
          <input
            id="min-score"
            type="range"
            min={0}
            max={100}
            step={MIN_SCORE_STEP}
            value={state.minScore ?? 0}
            onChange={(e) => {
              const n = Number(e.target.value);
              // 0 = no floor (inclusion over precision: don't drop unscored/low).
              set("minScore", n === 0 ? null : n);
            }}
            aria-label="Minimum match score"
            className="accent-[var(--zg-accent)]"
          />
          <span className="zg-num text-foreground w-8 text-xs tabular-nums">
            {state.minScore ?? 0}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <ToggleChip
            active={state.newOnly}
            onClick={() => set("newOnly", !state.newOnly)}
            label="New only"
          />
          <ToggleChip
            active={state.unscoredOnly}
            onClick={() => set("unscoredOnly", !state.unscoredOnly)}
            label="Unscored only"
          />
          <ToggleChip
            active={state.hideStale}
            onClick={() => set("hideStale", !state.hideStale)}
            label="Hide stale"
          />
          <ToggleChip
            active={state.payFloor}
            onClick={() => set("payFloor", !state.payFloor)}
            label="Meets pay floor"
          />
        </div>

        <div className="text-muted-foreground zg-num ml-auto text-xs">
          {summary}
        </div>
      </div>
    </div>
  );
}

function LabeledSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="flex items-center gap-1.5">
      <span className="text-muted-foreground sr-only text-xs sm:not-sr-only">
        {label}
      </span>
      <Select
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-auto min-w-[8rem]"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </Select>
    </label>
  );
}

/** Multi-select source filter — a dropdown of checkboxes. Empty selection = "all
 * sources" (the inclusion-over-precision default). The trigger summarizes the
 * selection count. */
function SourceMenu({
  selected,
  available,
  onChange,
}: {
  selected: string[];
  available: string[];
  onChange: (sources: string[]) => void;
}) {
  const selectedSet = new Set(selected);
  const toggle = (src: string) => {
    const next = new Set(selectedSet);
    if (next.has(src)) next.delete(src);
    else next.add(src);
    onChange(Array.from(next));
  };
  const label =
    selected.length === 0
      ? "All sources"
      : selected.length === 1
        ? sourceLabel(selected[0])
        : `${selected.length} sources`;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="h-9 justify-between gap-2"
          aria-label="Filter by source"
        >
          {label}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-72 overflow-y-auto">
        <DropdownMenuLabel>Sources</DropdownMenuLabel>
        {available.length === 0 ? (
          <p className="text-muted-foreground px-2 py-1.5 text-xs">
            No sources yet
          </p>
        ) : (
          <>
            {selected.length > 0 && (
              <>
                <button
                  type="button"
                  onClick={() => onChange([])}
                  className="text-primary hover:bg-accent w-full rounded-sm px-2 py-1.5 text-left text-xs"
                >
                  Clear selection (show all)
                </button>
                <DropdownMenuSeparator />
              </>
            )}
            {available.map((src) => (
              <DropdownMenuCheckboxItem
                key={src}
                checked={selectedSet.has(src)}
                onCheckedChange={() => toggle(src)}
                onSelect={(e) => e.preventDefault()}
              >
                {sourceLabel(src)}
              </DropdownMenuCheckboxItem>
            ))}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** A source id → a friendlier label (Title Case, known aliases). Presentational
 * only; the raw id is what's sent to the server. */
function sourceLabel(src: string): string {
  const known: Record<string, string> = {
    adzuna: "Adzuna",
    usajobs: "USAJOBS",
    jooble: "Jooble",
    remotive: "Remotive",
    careerjet: "Careerjet",
    themuse: "The Muse",
    greenhouse: "Greenhouse",
    lever: "Lever",
    ashby: "Ashby",
  };
  if (known[src]) return known[src];
  return src ? src.charAt(0).toUpperCase() + src.slice(1) : "Unknown";
}

function ToggleChip({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={active}
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[var(--radius-chip)] border px-2.5 py-1 text-xs font-medium transition-colors",
        "focus-visible:ring-ring/50 outline-none focus-visible:ring-2",
        active
          ? "border-primary/50 bg-primary/12 text-primary"
          : "border-border text-muted-foreground hover:text-foreground hover:border-ring/40",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "size-1.5 rounded-full",
          active ? "bg-primary" : "bg-muted-foreground/40",
        )}
      />
      {label}
    </button>
  );
}
