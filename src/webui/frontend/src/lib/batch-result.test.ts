import { describe, it, expect } from "vitest";
import {
  isBatchError,
  mapBatchResults,
  summarizeBatch,
  batchSummaryLine,
  type BatchResultEntry,
  type BatchRow,
} from "./batch-result";

const rows: BatchRow[] = [
  { id: 1, title: "Backend Eng", company: "Acme" },
  { id: 2, title: "Data Eng", company: "Globex" },
  { id: 3, title: "Platform Eng", company: "Initech" },
];

describe("isBatchError", () => {
  it("distinguishes error entries from file entries", () => {
    expect(isBatchError({ id: 1, error: "boom" })).toBe(true);
    expect(isBatchError({ id: 1, files: [] })).toBe(false);
  });
});

describe("mapBatchResults", () => {
  it("maps saved / failed / missing in batch order", () => {
    const ids = [1, 2, 3];
    const results: BatchResultEntry[] = [
      {
        id: 1,
        files: [
          {
            name: "resume_acme.docx",
            download_url: "/api/queue/download/resume_acme.docx",
          },
        ],
      },
      { id: 3, error: "DOCX render failed" },
      // id 2 absent -> the reply skipped that slot
    ];
    const out = mapBatchResults(ids, results, rows);
    expect(out).toHaveLength(3);
    expect(out[0]).toMatchObject({ id: 1, kind: "saved", company: "Acme" });
    expect(out[1]).toMatchObject({ id: 2, kind: "missing", company: "Globex" });
    expect(out[2]).toMatchObject({
      id: 3,
      kind: "failed",
      error: "DOCX render failed",
    });
    if (out[0].kind === "saved") {
      expect(out[0].files[0].download_url).toContain("/api/queue/download/");
    }
  });

  it("preserves the batch (ids) order regardless of results order", () => {
    const ids = [3, 1, 2];
    const results: BatchResultEntry[] = [
      { id: 1, files: [] },
      { id: 2, files: [] },
      { id: 3, files: [] },
    ];
    expect(mapBatchResults(ids, results, rows).map((o) => o.id)).toEqual([
      3, 1, 2,
    ]);
  });

  it("labels blank when a batched id isn't in the current rows", () => {
    const out = mapBatchResults([99], [{ id: 99, files: [] }], rows);
    expect(out[0]).toMatchObject({
      id: 99,
      title: "",
      company: "",
      kind: "saved",
    });
  });

  it("all-missing when results is empty", () => {
    const out = mapBatchResults([1, 2], [], rows);
    expect(out.every((o) => o.kind === "missing")).toBe(true);
  });
});

describe("summarizeBatch + batchSummaryLine", () => {
  const outcomes = mapBatchResults(
    [1, 2, 3],
    [
      { id: 1, files: [] },
      { id: 3, error: "boom" },
    ],
    rows,
  );

  it("counts saved / failed / missing / total", () => {
    expect(summarizeBatch(outcomes)).toEqual({
      saved: 1,
      failed: 1,
      missing: 1,
      total: 3,
    });
  });

  it("empty batch => empty summary line", () => {
    expect(batchSummaryLine([])).toBe("");
  });

  it("summary line reports saved/total and the missing hint", () => {
    const line = batchSummaryLine(outcomes);
    expect(line).toContain("Saved docs for 1/3 jobs.");
    expect(line).toContain("1 failed");
    expect(line).toContain("1 missing from the reply");
  });

  it("clean all-saved line has no failed/missing tail", () => {
    const clean = mapBatchResults(
      [1, 2],
      [
        { id: 1, files: [] },
        { id: 2, files: [] },
      ],
      rows,
    );
    expect(batchSummaryLine(clean)).toBe("Saved docs for 2/2 jobs.");
  });
});
