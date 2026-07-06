import { describe, it, expect } from "vitest";
import { daysInStageLabel } from "./board-labels";

/* The days-in-stage card line. The regression this guards: "today here" (the old
 * unconditional `${days_label} here`). */
describe("daysInStageLabel", () => {
  it("renders same-day cards naturally (not 'today here')", () => {
    expect(daysInStageLabel("today")).toBe("added today");
  });

  it("appends 'here' to a day count", () => {
    expect(daysInStageLabel("1 day")).toBe("1 day here");
    expect(daysInStageLabel("3 days")).toBe("3 days here");
    expect(daysInStageLabel("42 days")).toBe("42 days here");
  });

  it("blank in → blank out (caller omits the line)", () => {
    expect(daysInStageLabel("")).toBe("");
    expect(daysInStageLabel("   ")).toBe("");
  });
});
