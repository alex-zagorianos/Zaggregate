import { describe, it, expect } from "vitest";

import type {
  AiSetupApplied,
  AiSetupApplyResponse,
  ApplyAiSetupFullResponse,
} from "@/api/client";
import {
  configResult,
  fullResult,
  resultJobId,
  resultJobError,
  showsSeedRow,
} from "./ai-setup-logic";

/* The pure decision core behind the AI-setup panes: how a config vs full apply
 * response becomes an AiSetupResult, and what the wizard/dialog read off it
 * (job id to attach a console, job error to toast, whether to show a seeds row).
 * Component render/interaction isn't unit-testable here (node env, no RTL) — this
 * pins the behavior those components delegate to. */

const APPLIED: AiSetupApplied = {
  field: "mechanical engineering",
  target_titles: ["Design Engineer", "Mechanical Engineer"],
  location: "Cincinnati, OH",
  remote_only: false,
  salary_min: 85000,
  seniority: "mid",
  radius: 40,
  profile_chars: 1234,
};

const configResp: AiSetupApplyResponse = { ok: true, applied: APPLIED };

function fullResp(
  over: Partial<ApplyAiSetupFullResponse> = {},
): ApplyAiSetupFullResponse {
  return {
    ok: true,
    applied: APPLIED,
    seed_count: 0,
    job_id: null,
    ...over,
  };
}

describe("configResult / fullResult discrimination", () => {
  it("tags a config apply as kind 'config' carrying just applied", () => {
    const r = configResult(configResp);
    expect(r.kind).toBe("config");
    expect(r.applied).toBe(APPLIED);
  });
  it("tags a full apply as kind 'full' carrying seed_count + job_id", () => {
    const r = fullResult(fullResp({ seed_count: 12, job_id: "abc123" }));
    expect(r.kind).toBe("full");
    if (r.kind === "full") {
      expect(r.seed_count).toBe(12);
      expect(r.job_id).toBe("abc123");
    }
  });
});

describe("resultJobId — the console-attach handoff (apply → navigate with job)", () => {
  it("returns the started first-run job id for an autorun full apply", () => {
    const r = fullResult(fullResp({ seed_count: 5, job_id: "job-xyz" }));
    expect(resultJobId(r)).toBe("job-xyz");
  });
  it("is null for a config apply (no run to attach)", () => {
    expect(resultJobId(configResult(configResp))).toBeNull();
  });
  it("is null when autorun was false or a run was already in flight", () => {
    // autorun:false → job_id:null
    expect(resultJobId(fullResult(fullResp({ job_id: null })))).toBeNull();
    // JobConflict → job_id:null + job_error
    const conflict = fullResult(
      fullResp({ job_id: null, job_error: "another run is in progress" }),
    );
    expect(resultJobId(conflict)).toBeNull();
    expect(resultJobError(conflict)).toBe("another run is in progress");
  });
});

describe("resultJobError", () => {
  it("is undefined on a clean full apply and on any config apply", () => {
    expect(
      resultJobError(fullResult(fullResp({ job_id: "j" }))),
    ).toBeUndefined();
    expect(resultJobError(configResult(configResp))).toBeUndefined();
  });
});

describe("showsSeedRow — the applied summary's starter-companies row", () => {
  it("shows the seeds row only when a full reply carried seeds", () => {
    expect(showsSeedRow(fullResult(fullResp({ seed_count: 8 })))).toBe(true);
  });
  it("hides it for a config-only reply (no seeds concept)", () => {
    expect(showsSeedRow(configResult(configResp))).toBe(false);
  });
  it("hides it for a full reply with zero seeds (no '0 companies' row)", () => {
    expect(showsSeedRow(fullResult(fullResp({ seed_count: 0 })))).toBe(false);
  });
});
