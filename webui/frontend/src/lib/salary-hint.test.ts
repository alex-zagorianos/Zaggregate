import { describe, it, expect } from "vitest";
import { formatDollars, salaryHint } from "./salary-hint";

describe("formatDollars", () => {
  it("adds thousands separators, no cents", () => {
    expect(formatDollars(90000)).toBe("$90,000");
    expect(formatDollars(37440)).toBe("$37,440");
    expect(formatDollars(1234.7)).toBe("$1,235");
    expect(formatDollars(0)).toBe("$0");
  });
});

describe("salaryHint", () => {
  it("blank input → no hint", () => {
    expect(salaryHint(null, "none", "")).toBe("");
    expect(salaryHint(90000, "annual", "   ")).toBe("");
  });
  it("annual → a Minimum line", () => {
    expect(salaryHint(90000, "annual", "90k")).toBe("Minimum: $90,000 / yr");
  });
  it("hourly → an annualized echo", () => {
    expect(salaryHint(37440, "hourly", "18/hr")).toBe(
      "≈ $37,440 / yr  (annualized from an hourly rate)",
    );
  });
  it("bare-small number read as hourly annualizes", () => {
    // "18" with no unit → the server annualizes it (kind:'hourly').
    expect(salaryHint(37440, "hourly", "18")).toContain("≈ $37,440 / yr");
  });
  it("typed-but-unparseable → no hint (optional field, no nag)", () => {
    expect(salaryHint(null, "none", "competitive")).toBe("");
  });
});
