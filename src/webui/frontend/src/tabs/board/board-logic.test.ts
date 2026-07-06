import { describe, it, expect } from "vitest";
import {
  canDrop,
  isRealMove,
  rejectReason,
  type BoardCard,
} from "./board-logic";

const card = (status: string, forward_targets: string[]): BoardCard => ({
  id: 1,
  status,
  forward_targets,
});

/* Mirrors ui.kanban_core.forward_targets legality: a progression card advances to
 * the next step + any outcome; a terminal card advances nowhere. */
describe("canDrop", () => {
  const applied = card("applied", [
    "phone_screen",
    "offer",
    "accepted",
    "rejected",
    "withdrawn",
    "ghosted",
  ]);
  it("allows a listed forward target", () => {
    expect(canDrop(applied, "phone_screen")).toBe(true);
    expect(canDrop(applied, "rejected")).toBe(true);
  });
  it("allows a no-op drop onto its own column", () => {
    expect(canDrop(applied, "applied")).toBe(true);
  });
  it("rejects a target not in forward_targets (backwards move)", () => {
    expect(canDrop(applied, "interested")).toBe(false);
  });
  it("terminal card can only no-op", () => {
    const accepted = card("accepted", []);
    expect(canDrop(accepted, "accepted")).toBe(true);
    expect(canDrop(accepted, "rejected")).toBe(false);
  });
});

describe("isRealMove", () => {
  const applied = card("applied", ["phone_screen", "offer"]);
  it("true for a valid non-self target", () => {
    expect(isRealMove(applied, "phone_screen")).toBe(true);
  });
  it("false for a self drop (no-op)", () => {
    expect(isRealMove(applied, "applied")).toBe(false);
  });
  it("false for an invalid target", () => {
    expect(isRealMove(applied, "interested")).toBe(false);
  });
});

describe("rejectReason", () => {
  const label = (s: string) =>
    ({
      applied: "Applied",
      interested: "Interested",
      interview: "Interview",
      accepted: "Accepted",
    })[s] ?? s;
  it("explains a backwards move with from/to labels", () => {
    const applied = card("applied", ["interview"]);
    expect(rejectReason(applied, "interested", label)).toContain(
      "Applied → Interested",
    );
  });
  it("explains a terminal card specially", () => {
    const accepted = card("accepted", []);
    expect(rejectReason(accepted, "interested", label)).toContain(
      "final stage",
    );
  });
});
