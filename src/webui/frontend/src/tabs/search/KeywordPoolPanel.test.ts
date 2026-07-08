import { describe, it, expect } from "vitest";

import { mergeTermsCsv, yieldCopy, bucketPoolByTier } from "./KeywordPoolPanel";
import type { DiscoveryPoolRow } from "@/api/client";

/* KeywordPoolPanel has no component-render test infra available (vitest runs
 * in a node environment, no jsdom/RTL — see brain/techdebt-register-2026-07-05
 * .md #21 and components/states.test.tsx's same note). These pin the pure
 * logic extracted specifically so it's testable without rendering: the
 * jargon-free yield copy, the tier bucketing, and the roles/keywords merge. */

function row(overrides: Partial<DiscoveryPoolRow> = {}): DiscoveryPoolRow {
  return {
    id: 1,
    term: "Mechanic",
    tier: "core",
    source: "seed",
    status: "suggested",
    yield_count: null,
    yield_source: null,
    yield_date: null,
    first_seen: "2026-07-01T00:00:00+00:00",
    last_seen: "2026-07-01T00:00:00+00:00",
    activated_at: null,
    ...overrides,
  };
}

describe("yieldCopy", () => {
  it("shows nothing for a never-probed term", () => {
    expect(yieldCopy({ yield_date: null, yield_count: null })).toBeNull();
  });

  it("shows an approximate openings count when probed and positive", () => {
    expect(
      yieldCopy({ yield_date: "2026-07-07T00:00:00+00:00", yield_count: 54 }),
    ).toBe("~54 openings nearby");
  });

  it("uses the jargon-free 'hasn't found much lately' for a zero count", () => {
    expect(
      yieldCopy({ yield_date: "2026-07-07T00:00:00+00:00", yield_count: 0 }),
    ).toBe("hasn't found much lately");
  });

  it("uses the same copy for a probed-but-unknown count", () => {
    expect(
      yieldCopy({ yield_date: "2026-07-07T00:00:00+00:00", yield_count: null }),
    ).toBe("hasn't found much lately");
  });

  it("never renders raw jargon words", () => {
    const copy = yieldCopy({
      yield_date: "2026-07-07T00:00:00+00:00",
      yield_count: 12,
    });
    expect(copy?.toLowerCase()).not.toMatch(/probe|yield|marginal|soc/);
  });
});

describe("bucketPoolByTier", () => {
  it("buckets rows by tier into the three chip sections", () => {
    const pool = [
      row({ id: 1, term: "Mechanic", tier: "core" }),
      row({ id: 2, term: "Fleet Maintenance Tech", tier: "adjacent" }),
      row({ id: 3, term: "Field Service Technician", tier: "exploratory" }),
    ];
    const buckets = bucketPoolByTier(pool);
    expect(buckets.core.map((r) => r.term)).toEqual(["Mechanic"]);
    expect(buckets.adjacent.map((r) => r.term)).toEqual([
      "Fleet Maintenance Tech",
    ]);
    expect(buckets.exploratory.map((r) => r.term)).toEqual([
      "Field Service Technician",
    ]);
  });

  it("drops a negative-tier row (no section renders it)", () => {
    const pool = [
      row({ id: 1, term: "Mechanic", tier: "core" }),
      row({ id: 2, term: "Excluded Title", tier: "negative" }),
    ];
    const buckets = bucketPoolByTier(pool);
    expect(buckets.core).toHaveLength(1);
    expect(buckets.adjacent).toHaveLength(0);
    expect(buckets.exploratory).toHaveLength(0);
  });

  it("keeps a row in its origin tier regardless of active/suggested status", () => {
    const pool = [
      row({
        id: 1,
        term: "Fleet Maintenance Tech",
        tier: "adjacent",
        status: "active",
      }),
    ];
    const buckets = bucketPoolByTier(pool);
    expect(buckets.adjacent.map((r) => r.term)).toEqual([
      "Fleet Maintenance Tech",
    ]);
    expect(buckets.core).toHaveLength(0);
  });

  it("returns empty buckets for an empty pool", () => {
    const buckets = bucketPoolByTier([]);
    expect(buckets).toEqual({ core: [], adjacent: [], exploratory: [] });
  });
});

describe("mergeTermsCsv", () => {
  it("appends a genuinely-new term to an existing list", () => {
    expect(mergeTermsCsv("mechanical engineer", "welder")).toBe(
      "mechanical engineer, welder",
    );
  });

  it("dedupes case-insensitively, keeping the existing spelling", () => {
    expect(mergeTermsCsv("Mechanic", "mechanic")).toBe("Mechanic");
  });

  it("handles a blank existing list", () => {
    expect(mergeTermsCsv("", "welder, mechanic")).toBe("welder, mechanic");
  });

  it("handles a blank incoming list (no-op merge)", () => {
    expect(mergeTermsCsv("welder, mechanic", "")).toBe("welder, mechanic");
  });

  it("drops empty tokens from stray commas on either side", () => {
    expect(mergeTermsCsv("welder, ,", ", mechanic,")).toBe("welder, mechanic");
  });

  it("never drops an existing term (one-directional merge — union only)", () => {
    // Simulates: the panel's active set no longer includes "welder" (deactivated),
    // but the caller's existing roles text still has it typed — merge must not
    // silently remove anything the user typed themselves.
    expect(mergeTermsCsv("welder, mechanic", "mechanic")).toBe(
      "welder, mechanic",
    );
  });
});
