import { describe, it, expect } from "vitest";
import {
  clampShown,
  hasMore,
  nextShown,
  windowRows,
  shownSummary,
  DEFAULT_PAGE_SIZE,
} from "./window-rows";

describe("clampShown", () => {
  it("clamps into [0, total] and floors", () => {
    expect(clampShown(50, 100)).toBe(50);
    expect(clampShown(150, 100)).toBe(100);
    expect(clampShown(-5, 100)).toBe(0);
    expect(clampShown(50.9, 100)).toBe(50);
  });
  it("treats non-finite as 0 (safe default — never over-reveals on a bad value)", () => {
    expect(clampShown(Number.NaN, 100)).toBe(0);
    // Infinity is non-finite → the guard returns 0 rather than trusting it.
    expect(clampShown(Infinity, 100)).toBe(0);
  });
});

describe("hasMore / nextShown", () => {
  it("hasMore is true until everything is shown", () => {
    expect(hasMore(0, 250)).toBe(true);
    expect(hasMore(100, 250)).toBe(true);
    expect(hasMore(250, 250)).toBe(false);
    expect(hasMore(300, 250)).toBe(false);
    expect(hasMore(0, 0)).toBe(false);
  });

  it("nextShown bumps by the page size and clamps to total", () => {
    expect(nextShown(0, 250)).toBe(DEFAULT_PAGE_SIZE);
    expect(nextShown(100, 250)).toBe(200);
    expect(nextShown(200, 250)).toBe(250);
    // Idempotent at the end.
    expect(nextShown(250, 250)).toBe(250);
  });

  it("honors a custom page size", () => {
    expect(nextShown(0, 100, 25)).toBe(25);
    expect(nextShown(90, 100, 25)).toBe(100);
  });

  it("a full reveal followed by more steps stays at total", () => {
    let shown = 0;
    const total = 2000;
    for (let i = 0; i < 100; i++) shown = nextShown(shown, total);
    expect(shown).toBe(total);
    expect(hasMore(shown, total)).toBe(false);
  });
});

describe("windowRows", () => {
  const rows = Array.from({ length: 500 }, (_, i) => i);
  it("slices to the visible window without mutating input", () => {
    const w = windowRows(rows, 100);
    expect(w).toHaveLength(100);
    expect(w[0]).toBe(0);
    expect(w[99]).toBe(99);
    expect(rows).toHaveLength(500); // untouched
  });
  it("never over-slices past the array", () => {
    expect(windowRows(rows, 999)).toHaveLength(500);
    expect(windowRows(rows, 0)).toHaveLength(0);
  });
});

describe("shownSummary (inclusion over precision — always surfaces total)", () => {
  it("no filters, everything rendered → plain count", () => {
    expect(shownSummary(40, 40, 40)).toBe("40 jobs");
    expect(shownSummary(1, 1, 1)).toBe("1 job");
  });

  it("no filters, window hiding some → 'Showing X of Y'", () => {
    expect(shownSummary(100, 400, 400)).toBe("Showing 100 of 400");
  });

  it("filters narrowing, all filtered rendered → surfaces the unfiltered total", () => {
    // 30 survive the filter out of 400 total, all 30 in the DOM.
    expect(shownSummary(30, 30, 400)).toBe("30 of 400 shown");
  });

  it("filters AND a window both hiding → shows filtered and total", () => {
    expect(shownSummary(100, 300, 2000)).toBe(
      "Showing 100 of 300 filtered · 2,000 total",
    );
  });

  it("thousands are grouped", () => {
    expect(shownSummary(1500, 1500, 1500)).toBe("1,500 jobs");
  });
});
