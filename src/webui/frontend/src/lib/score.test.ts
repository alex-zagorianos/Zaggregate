import { describe, it, expect } from "vitest";
import { scoreBand, scoreNoteLabel } from "./score";

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

/* Parity with match/scorer.py::score_breakdown()'s return dict keys — the
 * Inbox detail pane's Score breakdown section renders exactly these. */
describe("scoreNoteLabel", () => {
  it("gives a friendly label for every known score_breakdown key", () => {
    expect(scoreNoteLabel("components")).toBe("Weighted components");
    expect(scoreNoteLabel("confidence")).toBe("Confidence");
    expect(scoreNoteLabel("size_adj")).toBe("Company-size adjustment");
    expect(scoreNoteLabel("board_count")).toBe("Boards seen on");
    expect(scoreNoteLabel("penalties")).toBe("Penalties");
  });

  it("falls back to a space-replaced key for an unknown key", () => {
    expect(scoreNoteLabel("some_future_key")).toBe("some future key");
  });
});
