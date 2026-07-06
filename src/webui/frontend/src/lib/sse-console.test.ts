import { describe, it, expect } from "vitest";
import {
  appendConsoleLine,
  appendConsoleLines,
  capConsole,
  isAtBottom,
} from "./sse-console";

/* The SSE run-console core. The load-bearing behavior is the BOUNDARY de-dupe from
 * JobRunner.replay_lines: an adjacent repeated line (replay tail meeting live
 * drain) is suppressed, but a genuine non-adjacent repeat is kept. */

describe("appendConsoleLine (adjacent-dup suppression)", () => {
  it("appends a distinct line", () => {
    expect(appendConsoleLine(["a"], "b")).toEqual(["a", "b"]);
  });

  it("suppresses a line identical to the immediately-preceding one", () => {
    // The replay/live boundary case: last replayed line == first live line.
    expect(appendConsoleLine(["a", "b"], "b")).toEqual(["a", "b"]);
  });

  it("keeps a non-adjacent repeat (legit duplicate pipeline output)", () => {
    expect(appendConsoleLine(["a", "b", "c"], "a")).toEqual([
      "a",
      "b",
      "c",
      "a",
    ]);
  });

  it("returns the same reference when suppressing (cheap setState no-op ok)", () => {
    const prev = ["x"];
    expect(appendConsoleLine(prev, "x")).toBe(prev);
  });

  it("appends into an empty console", () => {
    expect(appendConsoleLine([], "first")).toEqual(["first"]);
  });
});

describe("appendConsoleLines (batch fold)", () => {
  it("folds a batch, collapsing adjacent dups across the join and within", () => {
    // prev ends 'b'; batch starts 'b' (boundary dup) then has an internal dup.
    expect(appendConsoleLines(["a", "b"], ["b", "c", "c", "d"])).toEqual([
      "a",
      "b",
      "c",
      "d",
    ]);
  });

  it("keeps non-adjacent repeats within a batch", () => {
    expect(appendConsoleLines([], ["a", "b", "a"])).toEqual(["a", "b", "a"]);
  });
});

describe("capConsole", () => {
  it("keeps the last N lines when over the cap", () => {
    const lines = Array.from({ length: 2500 }, (_, i) => String(i));
    const capped = capConsole(lines, 2000);
    expect(capped).toHaveLength(2000);
    expect(capped[0]).toBe("500");
    expect(capped[1999]).toBe("2499");
  });
  it("returns input unchanged when within the cap", () => {
    const lines = ["a", "b"];
    expect(capConsole(lines, 2000)).toBe(lines);
  });
});

describe("isAtBottom (stick-to-bottom)", () => {
  it("is true at the exact bottom", () => {
    expect(isAtBottom(900, 1000, 100)).toBe(true);
  });
  it("is true within the tolerance", () => {
    expect(isAtBottom(880, 1000, 100, 24)).toBe(true); // 20px from bottom
  });
  it("is false when scrolled up past the tolerance", () => {
    expect(isAtBottom(500, 1000, 100, 24)).toBe(false);
  });
});
