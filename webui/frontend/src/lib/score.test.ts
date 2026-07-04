import { describe, it, expect } from "vitest";
import { scoreBand } from "./score";

/* Parity with ui/theme.py::score_band — the thresholds must match the engine
 * exactly so a chip's color agrees with the tk app on the same row. */
describe("scoreBand", () => {
  it("bands by the engine thresholds (good>=70, mid>=45, low>=0)", () => {
    expect(scoreBand(100)).toBe("good");
    expect(scoreBand(70)).toBe("good");
    expect(scoreBand(69)).toBe("mid");
    expect(scoreBand(45)).toBe("mid");
    expect(scoreBand(44)).toBe("low");
    expect(scoreBand(0)).toBe("low");
  });

  it("treats negative / missing / non-numeric as 'none' (unscored)", () => {
    expect(scoreBand(-1)).toBe("none");
    expect(scoreBand(null)).toBe("none");
    expect(scoreBand(undefined)).toBe("none");
    expect(scoreBand(Number.NaN)).toBe("none");
  });
});
