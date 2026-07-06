import { describe, it, expect } from "vitest";
import { hasInterviewHappened } from "./outreach-stage";

/* Guards the follow-up-vs-thank-you button label. The value is a hint only (the
 * server re-decides and returns the real `stage`), but the label must match the
 * common cases so the button doesn't mislead. */
describe("hasInterviewHappened", () => {
  it("is a plain follow-up before any interview", () => {
    expect(hasInterviewHappened("interested", 0)).toBe(false);
    expect(hasInterviewHappened("applied", 0)).toBe(false);
  });

  it("flips to thank-you once an interview stage is reached", () => {
    expect(hasInterviewHappened("phone_screen", 0)).toBe(true);
    expect(hasInterviewHappened("interview", 0)).toBe(true);
    expect(hasInterviewHappened("offer", 0)).toBe(true);
    expect(hasInterviewHappened("accepted", 0)).toBe(true);
  });

  it("flips to thank-you when a round is logged, regardless of status", () => {
    expect(hasInterviewHappened("applied", 1)).toBe(true);
    expect(hasInterviewHappened("interested", 2)).toBe(true);
  });

  it("terminal non-interview statuses stay follow-up when no round exists", () => {
    expect(hasInterviewHappened("rejected", 0)).toBe(false);
    expect(hasInterviewHappened("withdrawn", 0)).toBe(false);
    expect(hasInterviewHappened("ghosted", 0)).toBe(false);
  });

  it("tolerates casing / whitespace / empty", () => {
    expect(hasInterviewHappened(" Interview ", 0)).toBe(true);
    expect(hasInterviewHappened("", 0)).toBe(false);
  });
});
