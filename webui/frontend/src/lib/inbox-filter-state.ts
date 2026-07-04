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
