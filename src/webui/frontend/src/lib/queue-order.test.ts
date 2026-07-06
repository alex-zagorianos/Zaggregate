import { describe, it, expect } from "vitest";
import {
  rankValue,
  compareQueue,
  sortQueue,
  withRank,
  type QueueSortable,
} from "./queue-order";

describe("rankValue (Python `x or -1` parity)", () => {
  it("null / undefined => -1", () => {
    expect(rankValue(null)).toBe(-1);
    expect(rankValue(undefined)).toBe(-1);
  });
  it("0 is falsy in Python => -1", () => {
    expect(rankValue(0)).toBe(-1);
  });
  it("real numbers pass through", () => {
    expect(rankValue(70)).toBe(70);
    expect(rankValue(45)).toBe(45);
    expect(rankValue(1)).toBe(1);
  });
  it("non-finite => -1", () => {
    expect(rankValue(Number.NaN)).toBe(-1);
    expect(rankValue(Infinity)).toBe(-1);
  });
});

describe("compareQueue + sortQueue (parity with ApplyQueueTab.refresh)", () => {
  it("fit_score desc dominates", () => {
    const rows: QueueSortable[] = [
      { id: 1, fit_score: 40, score: 99 },
      { id: 2, fit_score: 80, score: 10 },
    ];
    const out = sortQueue(rows).map((r) => r.id);
    expect(out).toEqual([2, 1]);
  });

  it("score breaks the tie when fit is equal (both unscored)", () => {
    const rows: QueueSortable[] = [
      { id: 1, score: 55 },
      { id: 2, score: 72 },
      { id: 3, score: 60 },
    ];
    const out = sortQueue(rows).map((r) => r.id);
    expect(out).toEqual([2, 3, 1]);
  });

  it("a fit-scored row outranks any unscored row", () => {
    const rows: QueueSortable[] = [
      { id: 1, score: 99 }, // unscored fit -> -1
      { id: 2, fit_score: 10, score: 5 }, // fit 10
    ];
    const out = sortQueue(rows).map((r) => r.id);
    expect(out).toEqual([2, 1]);
  });

  it("matches the exact Python tuple sort on a mixed set", () => {
    // Python: sorted(reverse) by (fit or -1, score or -1)
    const rows: QueueSortable[] = [
      { id: "a", fit_score: null, score: 30 }, // (-1, 30)
      { id: "b", fit_score: 90, score: 0 }, // (90, -1)
      { id: "c", fit_score: 90, score: 88 }, // (90, 88)
      { id: "d", fit_score: null, score: null }, // (-1, -1)
      { id: "e", fit_score: 45, score: 45 }, // (45, 45)
    ];
    // Expected descending: c(90,88) b(90,-1) e(45,45) a(-1,30) d(-1,-1)
    expect(sortQueue(rows).map((r) => r.id)).toEqual(["c", "b", "e", "a", "d"]);
  });

  it("is stable for fully-equal ranks (preserves server order)", () => {
    const rows: QueueSortable[] = [
      { id: 1, fit_score: 50, score: 50 },
      { id: 2, fit_score: 50, score: 50 },
      { id: 3, fit_score: 50, score: 50 },
    ];
    expect(sortQueue(rows).map((r) => r.id)).toEqual([1, 2, 3]);
    expect(compareQueue(rows[0], rows[1])).toBe(0);
  });

  it("does not mutate the input array", () => {
    const rows: QueueSortable[] = [
      { id: 1, fit_score: 10 },
      { id: 2, fit_score: 90 },
    ];
    sortQueue(rows);
    expect(rows.map((r) => r.id)).toEqual([1, 2]);
  });
});

describe("withRank", () => {
  it("assigns 1-based ranks in input order (no re-sort)", () => {
    const ranked = withRank([{ id: "x" }, { id: "y" }, { id: "z" }]);
    expect(ranked.map((r) => r.rank)).toEqual([1, 2, 3]);
    expect(ranked.map((r) => r.id)).toEqual(["x", "y", "z"]);
  });
});
