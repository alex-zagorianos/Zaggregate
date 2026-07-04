import { describe, it, expect } from "vitest";
import { isValidDate, isValidScheduledAt, firstBadDate } from "./date-validate";

/* Parity with ui/common._DATE_RE + ui/job_dialog date checks: format-only
 * (^\d{4}-\d{2}-\d{2}$), empty allowed, round scheduled_at validates the leading
 * 10 chars so a bare date or an ISO datetime both pass. */
describe("isValidDate", () => {
  it("accepts a well-formed date or empty", () => {
    expect(isValidDate("2026-07-04")).toBe(true);
    expect(isValidDate("")).toBe(true);
    expect(isValidDate("   ")).toBe(true);
    expect(isValidDate(null)).toBe(true);
    expect(isValidDate(undefined)).toBe(true);
  });
  it("rejects malformed dates", () => {
    expect(isValidDate("07/04/2026")).toBe(false);
    expect(isValidDate("2026-7-4")).toBe(false);
    expect(isValidDate("July 4")).toBe(false);
    expect(isValidDate("2026-07-04T09:00")).toBe(false); // full date field is strict
  });
});

describe("isValidScheduledAt", () => {
  it("accepts a bare date, an ISO datetime, or empty", () => {
    expect(isValidScheduledAt("2026-07-04")).toBe(true);
    expect(isValidScheduledAt("2026-07-04T09:30")).toBe(true);
    expect(isValidScheduledAt("")).toBe(true);
  });
  it("rejects when the leading 10 chars aren't a date", () => {
    expect(isValidScheduledAt("tomorrow 9am")).toBe(false);
    expect(isValidScheduledAt("2026/07/04")).toBe(false);
  });
});

describe("firstBadDate", () => {
  it("returns null when every date field is valid/empty", () => {
    expect(
      firstBadDate({
        date_applied: "2026-07-04",
        follow_up_date: "",
        deadline: "2026-08-01",
        offer_deadline: "",
      }),
    ).toBeNull();
  });
  it("names the first offending field", () => {
    const bad = firstBadDate({
      date_applied: "2026-07-04",
      follow_up_date: "next week",
    });
    expect(bad).toEqual({ label: "Follow-up", value: "next week" });
  });
});
