import { describe, expect, it } from "vitest";

import {
  applyErrorMessage,
  checkMessage,
  classifyCheck,
  isTerminal,
  progressLabel,
  shouldKeepPolling,
} from "./update-flow";
import type { UpdateCheckResponse } from "@/api/client";

const base: UpdateCheckResponse = {
  ok: true,
  current: "1.0.2",
  latest: null,
  url: "https://github.com/alex-zagorianos/zaggregate/releases",
  newer: false,
  managed: false,
};

describe("classifyCheck", () => {
  it("offers the releases link for an unmanaged copy with a newer release", () => {
    const o = classifyCheck({ ...base, latest: "v1.0.3", newer: true });
    expect(o).toEqual({
      kind: "unmanaged",
      current: "1.0.2",
      latest: "v1.0.3",
      url: base.url,
    });
  });

  it("says up-to-date for an unmanaged copy on the latest release", () => {
    expect(classifyCheck({ ...base, latest: "v1.0.2" }).kind).toBe(
      "unmanaged-current",
    );
  });

  it("treats an unmanaged failed check as unavailable, not an error", () => {
    expect(classifyCheck(base).kind).toBe("unavailable");
  });

  it("offers a download for a managed copy with a newer release", () => {
    const o = classifyCheck({
      ...base,
      managed: true,
      latest: "1.0.3",
      newer: true,
    });
    expect(o).toEqual({ kind: "update-ready-to-download", latest: "1.0.3" });
  });

  it("prefers a staged update over re-downloading it", () => {
    // pending_restart wins even though `newer` is also true — the bits are on disk
    // already, possibly staged by a previous run of the app.
    const o = classifyCheck({
      ...base,
      managed: true,
      latest: "1.0.3",
      newer: true,
      pending_restart: true,
    });
    expect(o).toEqual({ kind: "already-downloaded", latest: "1.0.3" });
  });

  it("falls back to the current version when a staged update has no tag", () => {
    const o = classifyCheck({
      ...base,
      managed: true,
      newer: false,
      pending_restart: true,
    });
    expect(o).toEqual({ kind: "already-downloaded", latest: "1.0.2" });
  });

  it("says up-to-date for a managed copy already on the latest", () => {
    const o = classifyCheck({
      ...base,
      managed: true,
      latest: "1.0.2",
      newer: false,
    });
    expect(o).toEqual({ kind: "up-to-date", current: "1.0.2" });
  });

  it("treats a managed offline check as unavailable", () => {
    const o = classifyCheck({ ...base, managed: true, latest: null });
    expect(o.kind).toBe("unavailable");
  });
});

describe("polling predicates", () => {
  it("keeps polling only while work is in flight", () => {
    expect(shouldKeepPolling("checking")).toBe(true);
    expect(shouldKeepPolling("downloading")).toBe(true);
    expect(shouldKeepPolling("ready")).toBe(false);
    expect(shouldKeepPolling("error")).toBe(false);
    expect(shouldKeepPolling("idle")).toBe(false);
  });

  it("terminates on ready or error", () => {
    expect(isTerminal("ready")).toBe(true);
    expect(isTerminal("error")).toBe(true);
    expect(isTerminal("downloading")).toBe(false);
  });

  it("never keeps polling a terminal phase", () => {
    for (const p of [
      "idle",
      "checking",
      "downloading",
      "ready",
      "error",
    ] as const) {
      expect(shouldKeepPolling(p) && isTerminal(p)).toBe(false);
    }
  });
});

describe("progressLabel", () => {
  const p = (over: Partial<Parameters<typeof progressLabel>[0]>) =>
    progressLabel({
      ok: true,
      phase: "idle",
      percent: 0,
      version: null,
      failure: null,
      ...over,
    });

  it("shows the version and percent while downloading", () => {
    expect(p({ phase: "downloading", percent: 42, version: "1.0.3" })).toBe(
      "Downloading 1.0.3… 42%",
    );
  });

  it("omits an unknown version", () => {
    expect(p({ phase: "downloading", percent: 7 })).toBe("Downloading… 7%");
  });

  it("announces readiness", () => {
    expect(p({ phase: "ready", percent: 100, version: "1.0.3" })).toBe(
      "Version 1.0.3 is ready",
    );
  });

  it("reports a failure", () => {
    expect(p({ phase: "error", failure: "OSError: disk full" })).toBe(
      "Download failed",
    );
  });
});

describe("applyErrorMessage", () => {
  it("explains the daily-run interlock in the tester's terms", () => {
    const msg = applyErrorMessage({ ok: false, error: "daily-run-active" });
    expect(msg).toMatch(/daily search is running/i);
  });

  it("handles every known code and an unknown one", () => {
    for (const code of [
      "daily-run-active",
      "nothing-downloaded",
      "not-managed",
      "RuntimeError: boom",
      undefined,
    ]) {
      const msg = applyErrorMessage({ ok: false, error: code });
      expect(msg).toBeTruthy();
      expect(msg).not.toContain("undefined");
    }
  });

  it("reassures that a failed apply left the install alone", () => {
    expect(applyErrorMessage({ ok: false, error: "weird" })).toMatch(
      /current version is untouched/i,
    );
  });
});

describe("checkMessage", () => {
  it("returns null for outcomes that need an action button", () => {
    expect(
      checkMessage({ kind: "update-ready-to-download", latest: "1.0.3" }),
    ).toBeNull();
    expect(
      checkMessage({
        kind: "unmanaged",
        current: "1.0.2",
        latest: "v1.0.3",
        url: "u",
      }),
    ).toBeNull();
    expect(
      checkMessage({ kind: "already-downloaded", latest: "1.0.3" }),
    ).toBeNull();
  });

  it("returns copy for the passive outcomes", () => {
    expect(checkMessage({ kind: "up-to-date", current: "1.0.2" })).toContain(
      "1.0.2",
    );
    expect(checkMessage({ kind: "unavailable" })).toMatch(/no connection/i);
  });
});
