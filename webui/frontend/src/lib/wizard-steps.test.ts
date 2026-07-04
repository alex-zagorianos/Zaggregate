import { describe, it, expect } from "vitest";
import {
  WIZARD_STEPS,
  WIZARD_STEP_COUNT,
  FINISH_INDEX,
  EMPTY_ANSWERS,
  parseRoles,
  isStepValid,
  canAdvance,
  stepState,
  nextIndex,
  prevIndex,
  answersToPayload,
  industryToPickerValue,
  FIELD_OTHER,
  type WizardAnswers,
} from "./wizard-steps";

const withRoles = (roles: string): WizardAnswers => ({
  ...EMPTY_ANSWERS,
  roles,
});

describe("wizard step model", () => {
  it("has 7 ordered steps ending at Finish", () => {
    expect(WIZARD_STEP_COUNT).toBe(7);
    expect(WIZARD_STEPS[0].id).toBe("welcome");
    expect(WIZARD_STEPS[FINISH_INDEX].id).toBe("finish");
  });
});

describe("parseRoles", () => {
  it("splits, trims, and drops empties", () => {
    expect(parseRoles("  engineer , designer ,, ")).toEqual([
      "engineer",
      "designer",
    ]);
  });
  it("de-duplicates case-insensitively, keeping first spelling", () => {
    expect(parseRoles("Engineer, engineer, ENGINEER")).toEqual(["Engineer"]);
  });
  it("returns [] for blank", () => {
    expect(parseRoles("   ,  , ")).toEqual([]);
  });
});

describe("isStepValid", () => {
  it("gates Roles on at least one role", () => {
    expect(isStepValid("roles", withRoles(""))).toBe(false);
    expect(isStepValid("roles", withRoles("engineer"))).toBe(true);
  });
  it("treats every non-Roles step as always valid (inclusion over precision)", () => {
    for (const s of [
      "welcome",
      "ai-offer",
      "where",
      "resume",
      "sources",
      "finish",
    ] as const) {
      expect(isStepValid(s, EMPTY_ANSWERS)).toBe(true);
    }
  });
});

describe("canAdvance / nextIndex / prevIndex", () => {
  it("blocks advancing past the Roles step with no role", () => {
    const rolesIdx = WIZARD_STEPS.findIndex((s) => s.id === "roles");
    expect(canAdvance(rolesIdx, EMPTY_ANSWERS)).toBe(false);
    expect(nextIndex(rolesIdx, EMPTY_ANSWERS)).toBe(rolesIdx); // stays put
    expect(nextIndex(rolesIdx, withRoles("nurse"))).toBe(rolesIdx + 1);
  });
  it("clamps at the Finish step", () => {
    expect(nextIndex(FINISH_INDEX, withRoles("x"))).toBe(FINISH_INDEX);
  });
  it("back clamps at 0 and never validates", () => {
    expect(prevIndex(0)).toBe(0);
    expect(prevIndex(3)).toBe(2);
  });
  it("rejects out-of-range indices", () => {
    expect(canAdvance(-1, withRoles("x"))).toBe(false);
    expect(canAdvance(99, withRoles("x"))).toBe(false);
  });
});

describe("stepState (progress rail)", () => {
  it("marks the current step active, earlier valid steps done, later pending", () => {
    const a = withRoles("engineer");
    // At the Where step (index 3): welcome/ai-offer/roles are done, resume pending.
    expect(stepState(0, 3, a)).toBe("done");
    expect(stepState(2, 3, a)).toBe("done"); // roles valid
    expect(stepState(3, 3, a)).toBe("active");
    expect(stepState(4, 3, a)).toBe("pending");
  });
  it("does not mark an earlier INVALID step as done", () => {
    // Roles empty but somehow past it: it shows pending, not done.
    expect(stepState(2, 3, EMPTY_ANSWERS)).toBe("pending");
  });
});

describe("answersToPayload", () => {
  it("maps to the server POST shape (roles list, trimmed strings)", () => {
    const a: WizardAnswers = {
      ...EMPTY_ANSWERS,
      roles: "mechanical engineer, design engineer",
      location: "  Cincinnati, OH  ",
      remoteOk: false,
      salaryText: " 90k ",
      industry: " mechanical engineering ",
      level: "Mid",
      about: "  I like hardware.  ",
      resumeText: "raw resume",
    };
    expect(answersToPayload(a)).toEqual({
      roles: ["mechanical engineer", "design engineer"],
      location: "Cincinnati, OH",
      remote_ok: false,
      salary_min: "90k",
      industry: "mechanical engineering",
      level: "Mid",
      about: "I like hardware.",
      resume_text: "raw resume",
    });
  });
});

describe("industryToPickerValue", () => {
  it("keeps a known preset token as-is", () => {
    expect(industryToPickerValue("nursing")).toBe("nursing");
    expect(industryToPickerValue("  NURSING ")).toBe("nursing");
  });
  it("maps an unknown non-empty token to the Other sentinel", () => {
    expect(industryToPickerValue("underwater basket weaving")).toBe(
      FIELD_OTHER,
    );
  });
  it("keeps blank blank", () => {
    expect(industryToPickerValue("")).toBe("");
    expect(industryToPickerValue("   ")).toBe("");
  });
});
