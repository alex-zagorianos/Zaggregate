import { describe, it, expect } from "vitest";
import {
  makeDefaultFilters,
  toParams,
  activeFilterCount,
  isDefaultFilters,
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
