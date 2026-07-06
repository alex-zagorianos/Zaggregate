import { describe, it, expect } from "vitest";
import { ApiError } from "@/api/client";
import { friendlyError, friendlyServerError } from "./friendly-error";

describe("friendlyError", () => {
  it("uses an ApiError's own message", () => {
    const e = new ApiError("No API key configured", 409, null);
    expect(friendlyError(e)).toBe("No API key configured");
  });

  it("falls back to the default fallback for a non-ApiError", () => {
    expect(friendlyError(new Error("boom"))).toBe("Please try again.");
    expect(friendlyError("boom")).toBe("Please try again.");
    expect(friendlyError(undefined)).toBe("Please try again.");
  });

  it("honors a custom fallback", () => {
    expect(friendlyError(new Error("boom"), "Couldn't save.")).toBe(
      "Couldn't save.",
    );
  });

  it("falls back when an ApiError has an empty message", () => {
    const e = new ApiError("", 500, null);
    expect(friendlyError(e, "Server error.")).toBe("Server error.");
  });
});

describe("friendlyServerError", () => {
  it("passes through a normal one-line server message", () => {
    expect(friendlyServerError("Adzuna rate-limited us.")).toBe(
      "Adzuna rate-limited us.",
    );
  });

  it("falls back for blank / null / undefined", () => {
    expect(friendlyServerError("")).toBe(
      "The run failed — see the console log for details.",
    );
    expect(friendlyServerError(null)).toBe(
      "The run failed — see the console log for details.",
    );
    expect(friendlyServerError(undefined)).toBe(
      "The run failed — see the console log for details.",
    );
  });

  it("swaps a leaked traceback for the calm fallback", () => {
    const tb = "Traceback (most recent call last):\n  File x\nValueError: boom";
    expect(friendlyServerError(tb)).toBe(
      "The run failed — see the console log for details.",
    );
  });

  it("swaps a multi-line dump even without the word Traceback", () => {
    const multi = "line one\nline two\nline three";
    expect(friendlyServerError(multi)).toBe(
      "The run failed — see the console log for details.",
    );
  });

  it("keeps a short two-line message as-is", () => {
    const twoLines = "Connection failed.\nRetrying may help.";
    expect(friendlyServerError(twoLines)).toBe(twoLines);
  });

  it("honors a custom fallback", () => {
    expect(friendlyServerError("", "Something else broke.")).toBe(
      "Something else broke.",
    );
  });
});
