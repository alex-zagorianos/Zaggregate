import { describe, it, expect } from "vitest";
import {
  rowsFromCandidates,
  markValidating,
  applyVerdicts,
  reconcileUnverdicted,
  validatableCandidates,
  addEntries,
  addSummary,
  type DetectRow,
} from "./detect-table";
import type { CompanyCandidate, CompanyVerdictRow } from "@/api/client";

const CANDIDATES: CompanyCandidate[] = [
  {
    line: "Acme | https://boards.greenhouse.io/acme",
    name: "Acme",
    ats: "greenhouse",
    slug: "acme",
    status: "detected",
  },
  {
    line: "Globex careers",
    name: "Globex",
    ats: "direct",
    slug: "https://globex.com/careers",
    status: "direct",
  },
  { line: "just some prose", name: "", ats: "", slug: "", status: "dropped" },
];

describe("rowsFromCandidates", () => {
  it("maps detect statuses to phases, keeping dropped rows visible", () => {
    const rows = rowsFromCandidates(CANDIDATES);
    expect(rows.map((r) => r.phase)).toEqual(["detected", "direct", "dropped"]);
    expect(rows[2].line).toBe("just some prose");
  });
});

describe("markValidating", () => {
  it("spins detectable rows, leaves direct + dropped untouched", () => {
    const rows = markValidating(rowsFromCandidates(CANDIDATES));
    expect(rows[0].phase).toBe("validating");
    expect(rows[1].phase).toBe("direct");
    expect(rows[2].phase).toBe("dropped");
  });
});

describe("applyVerdicts", () => {
  it("overlays verdicts by slug", () => {
    const rows = markValidating(rowsFromCandidates(CANDIDATES));
    const verdicts: CompanyVerdictRow[] = [
      {
        name: "Acme",
        ats: "greenhouse",
        slug: "acme",
        verdict: "live",
        count: 12,
        detail: "live (12 open jobs)",
      },
    ];
    const out = applyVerdicts(rows, verdicts);
    expect(out[0].phase).toBe("live");
    expect(out[0].count).toBe(12);
    expect(out[0].detail).toBe("live (12 open jobs)");
    // Unmatched (direct/dropped) rows untouched.
    expect(out[1].phase).toBe("direct");
  });
  it("maps an unreachable verdict", () => {
    const rows: DetectRow[] = [
      {
        line: "x",
        name: "Dead",
        ats: "lever",
        slug: "dead",
        phase: "validating",
        detail: "",
      },
    ];
    const out = applyVerdicts(rows, [
      {
        name: "Dead",
        ats: "lever",
        slug: "dead",
        verdict: "unreachable",
        detail: "walled",
      },
    ]);
    expect(out[0].phase).toBe("unreachable");
  });
});

describe("reconcileUnverdicted", () => {
  it("reverts a still-spinning row to detected (cancelled mid-run)", () => {
    const rows: DetectRow[] = [
      {
        line: "a",
        name: "A",
        ats: "greenhouse",
        slug: "a",
        phase: "validating",
        detail: "",
      },
      {
        line: "b",
        name: "B",
        ats: "greenhouse",
        slug: "b",
        phase: "live",
        detail: "live",
      },
    ];
    const out = reconcileUnverdicted(rows);
    expect(out[0].phase).toBe("detected");
    expect(out[1].phase).toBe("live");
  });
});

describe("validatableCandidates", () => {
  it("excludes dropped rows", () => {
    const rows = rowsFromCandidates(CANDIDATES);
    const c = validatableCandidates(rows);
    expect(c.map((x) => x.slug)).toEqual([
      "acme",
      "https://globex.com/careers",
    ]);
  });
});

describe("addEntries", () => {
  it("maps phases to gate verdicts and tags industry", () => {
    const rows: DetectRow[] = [
      {
        line: "a",
        name: "A",
        ats: "greenhouse",
        slug: "a",
        phase: "live",
        detail: "",
      },
      {
        line: "b",
        name: "B",
        ats: "direct",
        slug: "b",
        phase: "direct",
        detail: "",
      },
      {
        line: "c",
        name: "C",
        ats: "lever",
        slug: "c",
        phase: "unreachable",
        detail: "",
      },
      {
        line: "d",
        name: "D",
        ats: "greenhouse",
        slug: "d",
        phase: "detected",
        detail: "",
      },
      { line: "e", name: "", ats: "", slug: "", phase: "dropped", detail: "" },
    ];
    const out = addEntries(rows, "nursing");
    expect(out.map((e) => [e.slug, e.verdict])).toEqual([
      ["a", "live"],
      ["b", "direct"],
      ["c", "unreachable"],
      ["d", "unreachable"], // never-validated → gated, never silently verified
    ]);
    expect(out.every((e) => e.industry === "nursing")).toBe(true);
    // Dropped/slug-less rows excluded.
    expect(out.find((e) => e.slug === "")).toBeUndefined();
  });
  it("omits industry when blank", () => {
    const rows: DetectRow[] = [
      {
        line: "a",
        name: "A",
        ats: "greenhouse",
        slug: "a",
        phase: "live",
        detail: "",
      },
    ];
    expect(addEntries(rows)[0].industry).toBeUndefined();
  });
});

describe("addSummary", () => {
  const rows: DetectRow[] = [
    {
      line: "a",
      name: "A",
      ats: "greenhouse",
      slug: "a",
      phase: "live",
      detail: "",
    },
    {
      line: "b",
      name: "B",
      ats: "direct",
      slug: "b",
      phase: "direct",
      detail: "",
    },
    {
      line: "c",
      name: "C",
      ats: "lever",
      slug: "c",
      phase: "unreachable",
      detail: "",
    },
    { line: "d", name: "", ats: "", slug: "", phase: "dropped", detail: "" },
  ];
  it("counts live/unreachable/dropped and gates willAdd on keepUnreachable", () => {
    expect(addSummary(rows, false)).toEqual({
      live: 2,
      unreachable: 1,
      dropped: 1,
      willAdd: 2,
    });
    expect(addSummary(rows, true)).toEqual({
      live: 2,
      unreachable: 1,
      dropped: 1,
      willAdd: 3,
    });
  });
});
