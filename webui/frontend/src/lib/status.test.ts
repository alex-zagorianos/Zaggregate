import { describe, it, expect } from "vitest";
import { statusVar, statusLabel, isTerminal } from "./status";

describe("statusVar", () => {
  it("maps a status to its --zg-status-* token, underscores → hyphens", () => {
    expect(statusVar("interested")).toBe("var(--zg-status-interested)");
    expect(statusVar("phone_screen")).toBe("var(--zg-status-phone-screen)");
  });
  it("falls back to a neutral token for empty/missing", () => {
    expect(statusVar("")).toBe("var(--zg-status-withdrawn)");
    expect(statusVar(null)).toBe("var(--zg-status-withdrawn)");
    expect(statusVar(undefined)).toBe("var(--zg-status-withdrawn)");
  });
});

describe("statusLabel", () => {
  const labels = {
    interested: "Interested",
    phone_screen: "Phone Screen",
  };
  it("prefers the server-provided label map", () => {
    expect(statusLabel("phone_screen", labels)).toBe("Phone Screen");
  });
  it("Title-Cases the raw key when no map entry exists", () => {
    expect(statusLabel("phone_screen")).toBe("Phone Screen");
    expect(statusLabel("interested", {})).toBe("Interested");
    expect(statusLabel("some_new_status")).toBe("Some New Status");
  });
  it("returns an em-dash for empty status", () => {
    expect(statusLabel("")).toBe("—");
    expect(statusLabel(null)).toBe("—");
  });
});

describe("isTerminal", () => {
  it("flags the four outcome stages", () => {
    for (const s of ["accepted", "rejected", "withdrawn", "ghosted"]) {
      expect(isTerminal(s)).toBe(true);
    }
  });
  it("is false for progression stages", () => {
    for (const s of [
      "interested",
      "applied",
      "phone_screen",
      "interview",
      "offer",
    ]) {
      expect(isTerminal(s)).toBe(false);
    }
  });
});
