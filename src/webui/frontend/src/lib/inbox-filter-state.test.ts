import { describe, it, expect } from "vitest";
import {
  makeDefaultFilters,
  toParams,
  activeFilterCount,
  isDefaultFilters,
  filtersToUrlParams,
  filtersFromUrlParams,
  type InboxFilterState,
} from "./inbox-filter-state";

/* The Inbox filter-bar's pure core. The load-bearing property is
 * INCLUSION OVER PRECISION: the default state must send NO narrowing params so the
 * server returns the whole inbox, and every field at its default must be a no-op. */

describe("makeDefaultFilters / toParams (inclusion over precision)", () => {
  it("the default state sends only the sort + location default — no narrowing", () => {
    const p = toParams(makeDefaultFilters());
    // No min_score, no sources, no size, no q, no boolean narrowers.
    expect(p.min_score).toBeUndefined();
    expect(p.sources).toBeUndefined();
    expect(p.size).toBeUndefined();
    expect(p.q).toBeUndefined();
    expect(p.new_only).toBeUndefined();
    expect(p.unscored_only).toBeUndefined();
    expect(p.hide_stale).toBeUndefined();
    expect(p.pay_floor).toBeUndefined();
    // order is always present (a sort, server-validated); location default is sent.
    expect(p.order).toBe("roundrobin");
    expect(p.location_mode).toBe("Local + remote");
  });

  it("each default is a fresh object (no shared mutable state)", () => {
    const a = makeDefaultFilters();
    a.sources.push("adzuna");
    expect(makeDefaultFilters().sources).toEqual([]);
  });

  it("maps active filters to the exact server params", () => {
    const s: InboxFilterState = {
      minScore: 60,
      sources: ["adzuna", "usajobs"],
      size: "L",
      locationMode: "Local only",
      payFloor: true,
      q: "  controls engineer  ",
      newOnly: true,
      unscoredOnly: true,
      hideStale: true,
      order: "score",
    };
    expect(toParams(s)).toEqual({
      min_score: 60,
      sources: "adzuna,usajobs",
      size: "L",
      location_mode: "Local only",
      pay_floor: true,
      q: "controls engineer",
      new_only: true,
      unscored_only: true,
      hide_stale: true,
      order: "score",
    });
  });

  it("size 'All' and empty search are no-ops", () => {
    const s = makeDefaultFilters();
    s.size = "All";
    s.q = "   ";
    const p = toParams(s);
    expect(p.size).toBeUndefined();
    expect(p.q).toBeUndefined();
  });

  it("a non-finite minScore is dropped (never sent as NaN)", () => {
    const s = makeDefaultFilters();
    s.minScore = Number.NaN;
    expect(toParams(s).min_score).toBeUndefined();
  });
});

describe("activeFilterCount / isDefaultFilters", () => {
  it("the default view has zero active filters", () => {
    const s = makeDefaultFilters();
    expect(activeFilterCount(s)).toBe(0);
    expect(isDefaultFilters(s)).toBe(true);
  });

  it("neither the default location nor the sort order counts as a narrower", () => {
    const s = makeDefaultFilters();
    s.order = "score"; // a sort, not a filter
    expect(activeFilterCount(s)).toBe(0);
    // ...but the state is no longer the pristine baseline (order changed).
    expect(isDefaultFilters(s)).toBe(false);
  });

  it("'All locations' is an explicit no-op and does not count", () => {
    const s = makeDefaultFilters();
    s.locationMode = "All locations";
    expect(activeFilterCount(s)).toBe(0);
  });

  it("'Local only' narrows and counts", () => {
    const s = makeDefaultFilters();
    s.locationMode = "Local only";
    expect(activeFilterCount(s)).toBe(1);
  });

  it("counts each independent narrower once", () => {
    const s: InboxFilterState = {
      minScore: 50,
      sources: ["adzuna"],
      size: "S",
      locationMode: "Local only",
      payFloor: true,
      q: "x",
      newOnly: true,
      unscoredOnly: true,
      hideStale: true,
      order: "roundrobin",
    };
    expect(activeFilterCount(s)).toBe(9);
    expect(isDefaultFilters(s)).toBe(false);
  });
});

describe("filtersToUrlParams / filtersFromUrlParams (URL sync)", () => {
  it("the default state serializes to an empty query string (clean URLs)", () => {
    const p = filtersToUrlParams(makeDefaultFilters());
    expect(p.toString()).toBe("");
  });

  it("round-trips a fully-narrowed state through the URL and back", () => {
    const s: InboxFilterState = {
      minScore: 60,
      sources: ["adzuna", "usajobs"],
      size: "L",
      locationMode: "Local only",
      payFloor: true,
      q: "controls engineer",
      newOnly: true,
      unscoredOnly: true,
      hideStale: true,
      order: "score",
    };
    const params = filtersToUrlParams(s);
    const roundTripped = filtersFromUrlParams(params);
    expect(roundTripped).toEqual(s);
  });

  it("round-trips each location mode (including the non-default 'All locations')", () => {
    for (const locationMode of [
      "Local + remote",
      "Local only",
      "All locations",
    ] as const) {
      const s = { ...makeDefaultFilters(), locationMode };
      const params = filtersToUrlParams(s);
      expect(filtersFromUrlParams(params).locationMode).toBe(locationMode);
    }
  });

  it("round-trips a lone search query (trims whitespace, same as toParams)", () => {
    const s = { ...makeDefaultFilters(), q: "  react developer  " };
    const params = filtersToUrlParams(s);
    expect(params.get("q")).toBe("react developer");
    expect(filtersFromUrlParams(params).q).toBe("react developer");
  });

  it("omits every default-valued field from the URL", () => {
    const s = makeDefaultFilters();
    s.q = "python"; // the one narrower set
    const params = filtersToUrlParams(s);
    expect(Array.from(params.keys())).toEqual(["q"]);
    expect(params.toString()).toBe("q=python");
  });

  it("garbage band/size/loc/sort values fall back to defaults, not a crash", () => {
    const params = new URLSearchParams({
      band: "not-a-number",
      size: "GIANT",
      loc: "mars",
      sort: "chaos",
    });
    const state = filtersFromUrlParams(params);
    expect(state).toEqual(makeDefaultFilters());
  });

  it("an out-of-range band (negative or >100) falls back to no floor", () => {
    expect(
      filtersFromUrlParams(new URLSearchParams({ band: "-5" })).minScore,
    ).toBeNull();
    expect(
      filtersFromUrlParams(new URLSearchParams({ band: "500" })).minScore,
    ).toBeNull();
  });

  it("unknown query keys are ignored (never throw)", () => {
    const params = new URLSearchParams({
      utm_source: "newsletter",
      band: "70",
    });
    expect(() => filtersFromUrlParams(params)).not.toThrow();
    expect(filtersFromUrlParams(params).minScore).toBe(70);
  });

  it("an empty query string yields the exact default filter state", () => {
    expect(filtersFromUrlParams(new URLSearchParams())).toEqual(
      makeDefaultFilters(),
    );
  });

  it("blank sources entries (trailing/double commas) are dropped, not kept as empty strings", () => {
    const params = new URLSearchParams({ sources: "adzuna,,usajobs," });
    expect(filtersFromUrlParams(params).sources).toEqual(["adzuna", "usajobs"]);
  });
});
