import { describe, it, expect } from "vitest";
import { filterCommands } from "./filter-commands";

/* Parity with ui/palette.py::filter_commands. These cases mirror the Python
 * contract: substring-position-first, then subsequence, then alpha. */
describe("filterCommands", () => {
  const labels = [
    "Go to Inbox",
    "Go to Top Picks",
    "Go to Search",
    "Go to Apply Queue",
    "Go to Tracker",
    "Toggle dark mode",
    "Open the Guide",
  ] as const;

  it("empty query returns all in original order", () => {
    expect(filterCommands(labels, "")).toEqual([...labels]);
    expect(filterCommands(labels, "   ")).toEqual([...labels]);
  });

  it("is case-insensitive", () => {
    expect(filterCommands(labels, "INBOX")).toContain("Go to Inbox");
  });

  it("substring matches beat subsequence matches", () => {
    // "tk" is a substring of nothing but a subsequence of "Go to Tracker"
    // ("...t...k..."). "dark" is a direct substring of "Toggle dark mode".
    const res = filterCommands(labels, "dark");
    expect(res[0]).toBe("Toggle dark mode");
  });

  it("earlier substring position ranks first", () => {
    // query "o": "Open the Guide" has 'o'/'O' — but matching is lowercased, so
    // "Open the Guide" -> pos 0; "Go to Inbox" -> pos 1. Earlier wins.
    const res = filterCommands(["Go to Inbox", "Open the Guide"], "o");
    expect(res[0]).toBe("Open the Guide");
  });

  it("ties break alphabetically (case-insensitive)", () => {
    // Both contain "go to " at pos 0 -> tie on tier+pos -> alpha order.
    const res = filterCommands(
      ["Go to Search", "Go to Inbox", "Go to Apply Queue"],
      "go to ",
    );
    expect(res).toEqual(["Go to Apply Queue", "Go to Inbox", "Go to Search"]);
  });

  it("subsequence match works when no substring exists", () => {
    // "gtq" is not a substring but IS a subsequence of "Go to Apply Queue"
    // (G..t..Queue) and "Go to Tracker"? no q. Only the Queue matches.
    const res = filterCommands(labels, "gtq");
    expect(res).toContain("Go to Apply Queue");
    expect(res).not.toContain("Go to Tracker");
  });

  it("non-matching query returns empty", () => {
    expect(filterCommands(labels, "zzzz")).toEqual([]);
  });
});
