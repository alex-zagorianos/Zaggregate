/* Inbox filter state <-> query-param mapping — the pure core the flagship Inbox
 * tab's filter bar is built on. Kept out of the component (and unit-tested in
 * inbox-filter-state.test.ts, node env) so the exact mapping to the GET /api/inbox
 * params is verifiable without a DOM.
 *
 * INCLUSION OVER PRECISION (repo CLAUDE.md, plan Global constraints): every field
 * here is a VIEW filter. The default state is "show everything" — every param is a
 * no-op at its default, and `toParams` OMITS a param entirely when it's at its
 * default so the server keeps the row. Nothing here can hard-drop a job; dismiss /
 * track / view-mode are the only drop mechanisms. The one intentional hide is the
 * opt-in `payFloor` toggle (mirrors the tk "Meets pay floor" checkbox — reversible,
 * off by default), which the server resolves against the project's own floor.
 *
 * The server contract (webui/api/inbox.py::list_inbox): params min_score, sources
 * (csv), size (S/M/L/XL/?), location_mode, pay_floor (bool), q, new_only,
 * unscored_only, hide_stale, order (roundrobin|score), limit, offset. */

/** The three location modes the engine ships (geo.filter.LOCATION_MODES). "All
 * locations" disables the location view filter entirely (never hides a row). */
export const LOCATION_MODES = [
  "Local + remote",
  "Local only",
  "All locations",
] as const;
export type LocationMode = (typeof LOCATION_MODES)[number];

/** The company-size letters (match.inbox_filters.size_letter) plus "All". */
export const SIZE_OPTIONS = ["All", "S", "M", "L", "XL", "?"] as const;
export type SizeOption = (typeof SIZE_OPTIONS)[number];

/** Round-robin (diverse, the tk default) vs. score-descending ordering. */
export type InboxOrder = "roundrobin" | "score";

/** The complete Inbox filter-bar state. The DEFAULTS are the "show everything"
 * view: no minimum score, every source, all sizes, local+remote (the engine
 * default, which — with no home metro — the server short-circuits to All), pay
 * floor OFF, no search, all the boolean narrowers OFF. */
export interface InboxFilterState {
  /** Minimum base match score (0–100); null = no floor. */
  minScore: number | null;
  /** Selected source ids; empty = every source (the tk "All"). */
  sources: string[];
  size: SizeOption;
  locationMode: LocationMode;
  /** Opt-in "only rows whose disclosed pay clears my floor" (server-resolved). */
  payFloor: boolean;
  /** Free-text search over title OR company (server ?q=). */
  q: string;
  /** Only the latest fresh batch. */
  newOnly: boolean;
  /** Only still-unscored rows (fit < 0). */
  unscoredOnly: boolean;
  /** Drop rows the ghost-checker flagged 'stale'. */
  hideStale: boolean;
  order: InboxOrder;
}

/** The everything-shown baseline. `makeDefaultFilters()` returns a fresh copy so
 * callers can freely mutate their state object. */
export function makeDefaultFilters(): InboxFilterState {
  return {
    minScore: null,
    sources: [],
    size: "All",
    locationMode: "Local + remote",
    payFloor: false,
    q: "",
    newOnly: false,
    unscoredOnly: false,
    hideStale: false,
    order: "roundrobin",
  };
}

/** Params object the api client's `params` option accepts (undefined = dropped). */
export type InboxQueryParams = Record<
  string,
  string | number | boolean | undefined
>;

/** Map filter state -> GET /api/inbox query params. A field at its default is
 * OMITTED (undefined) so it's a server-side no-op — the inclusion-over-precision
 * guarantee lives here: the empty state sends essentially nothing and the server
 * returns the full inbox. `order` is always sent (it's a sort, not a filter, and
 * the server validates it). */
export function toParams(state: InboxFilterState): InboxQueryParams {
  const p: InboxQueryParams = {};
  if (state.minScore !== null && Number.isFinite(state.minScore)) {
    p.min_score = state.minScore;
  }
  if (state.sources.length > 0) p.sources = state.sources.join(",");
  if (state.size && state.size !== "All") p.size = state.size;
  // "Local + remote" is the engine default; still send it so the server applies
  // the mode the user sees. "All locations" is a no-op server-side (short-circuit).
  if (state.locationMode) p.location_mode = state.locationMode;
  if (state.payFloor) p.pay_floor = true;
  const q = state.q.trim();
  if (q) p.q = q;
  if (state.newOnly) p.new_only = true;
  if (state.unscoredOnly) p.unscored_only = true;
  if (state.hideStale) p.hide_stale = true;
  p.order = state.order;
  return p;
}

/** How many filters are "active" (narrowing the view away from the default) — the
 * number the filter-bar's count chip shows and the Clear button resets. `order`
 * and the always-present location default do NOT count (they don't narrow). Pay
 * floor, a non-default size, a min score, any source selection, a search, and each
 * boolean narrower each count as one. */
export function activeFilterCount(state: InboxFilterState): number {
  let n = 0;
  if (state.minScore !== null) n++;
  if (state.sources.length > 0) n++;
  if (state.size !== "All") n++;
  // Location only counts when it actually narrows (not the wide-open default and
  // not the explicit "All locations" no-op).
  if (state.locationMode === "Local only") n++;
  if (state.payFloor) n++;
  if (state.q.trim()) n++;
  if (state.newOnly) n++;
  if (state.unscoredOnly) n++;
  if (state.hideStale) n++;
  return n;
}

/** True when the state is the everything-shown baseline (no active narrower and
 * the default order). Used to enable/disable the Clear button. */
export function isDefaultFilters(state: InboxFilterState): boolean {
  return activeFilterCount(state) === 0 && state.order === "roundrobin";
}

// ── URL sync (KNOWN_ISSUES: "Filter state not URL-synced") ─────────────────────
//
// The browser's address bar, not the server, is the sync target here — these are
// SHORT param names (q/band/loc/... ) distinct from `toParams`'s server-shaped
// names (min_score/location_mode/...), kept deliberately terse for a readable URL
// like /app/inbox?q=engineer&band=60&loc=local&sort=score. Default-valued fields
// are omitted (clean URLs; `/app/inbox` when everything is default) and parsing is
// FAIL-OPEN: any missing/garbage value falls back to that field's default rather
// than throwing or partially applying — a hand-edited or stale URL can never crash
// the tab or filter out the whole inbox.

const LOCATION_URL: Record<LocationMode, string> = {
  "Local + remote": "localremote",
  "Local only": "local",
  "All locations": "all",
};
const LOCATION_FROM_URL: Record<string, LocationMode> = Object.fromEntries(
  Object.entries(LOCATION_URL).map(([mode, key]) => [
    key,
    mode as LocationMode,
  ]),
);

const SIZE_URL_VALUES = new Set<string>(SIZE_OPTIONS);
const ORDER_URL_VALUES = new Set(["roundrobin", "score"]);

/** InboxFilterState -> URL query params. Every default-valued field is omitted. */
export function filtersToUrlParams(state: InboxFilterState): URLSearchParams {
  const p = new URLSearchParams();
  if (state.minScore !== null && Number.isFinite(state.minScore)) {
    p.set("band", String(state.minScore));
  }
  if (state.sources.length > 0) p.set("sources", state.sources.join(","));
  if (state.size !== "All") p.set("size", state.size);
  if (state.locationMode !== "Local + remote") {
    p.set("loc", LOCATION_URL[state.locationMode]);
  }
  if (state.payFloor) p.set("payFloor", "1");
  const q = state.q.trim();
  if (q) p.set("q", q);
  if (state.newOnly) p.set("new", "1");
  if (state.unscoredOnly) p.set("unscored", "1");
  if (state.hideStale) p.set("hideStale", "1");
  if (state.order !== "roundrobin") p.set("sort", state.order);
  return p;
}

/** URL query params -> InboxFilterState. Fail-open: unknown keys are ignored and
 * any garbage/unparsable value for a known key silently falls back to that
 * field's default (never throws, never yields a state that hides everything). */
export function filtersFromUrlParams(
  params: URLSearchParams,
): InboxFilterState {
  const state = makeDefaultFilters();

  const band = params.get("band");
  if (band !== null) {
    const n = Number(band);
    if (Number.isFinite(n) && n > 0 && n <= 100) state.minScore = n;
  }

  const sources = params.get("sources");
  if (sources) {
    state.sources = sources
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  const size = params.get("size");
  if (size && SIZE_URL_VALUES.has(size)) state.size = size as SizeOption;

  const loc = params.get("loc");
  if (loc && LOCATION_FROM_URL[loc])
    state.locationMode = LOCATION_FROM_URL[loc];

  if (params.get("payFloor") === "1") state.payFloor = true;

  const q = params.get("q");
  if (q) state.q = q;

  if (params.get("new") === "1") state.newOnly = true;
  if (params.get("unscored") === "1") state.unscoredOnly = true;
  if (params.get("hideStale") === "1") state.hideStale = true;

  const sort = params.get("sort");
  if (sort && ORDER_URL_VALUES.has(sort)) state.order = sort as InboxOrder;

  return state;
}
