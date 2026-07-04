import { describe, it, expect } from "vitest";
import {
  EVENT_PREFIX,
  parseLine,
  classifySource,
  reduceProgress,
  emptyProgress,
  progressFraction,
  healthCounts,
  type ProgressEvent,
} from "./search-progress";

describe("EVENT_PREFIX (must equal backend search.EVENT_PREFIX)", () => {
  it("is the literal '@event ' sentinel with a trailing space", () => {
    expect(EVENT_PREFIX).toBe("@event ");
  });
});

describe("parseLine", () => {
  it("parses a well-formed structured frame into an event", () => {
    const p = parseLine('@event {"phase":"start","total":8}');
    expect(p.kind).toBe("event");
    if (p.kind === "event") {
      expect(p.event.phase).toBe("start");
      expect((p.event as { total: number }).total).toBe(8);
    }
  });

  it("treats a line without the prefix as plain text", () => {
    const p = parseLine("1 result(s).");
    expect(p).toEqual({ kind: "plain", text: "1 result(s)." });
  });

  it("treats a prefixed-but-malformed-JSON line as plain (never throws)", () => {
    const raw = "@event {not json";
    const p = parseLine(raw);
    expect(p).toEqual({ kind: "plain", text: raw });
  });

  it("treats a prefixed JSON object WITHOUT a phase as plain", () => {
    const raw = '@event {"foo":1}';
    expect(parseLine(raw).kind).toBe("plain");
  });

  it("does not treat a bare human line that merely contains 'event' as a frame", () => {
    expect(parseLine("scraping event boards…").kind).toBe("plain");
  });
});

describe("classifySource (parity with tab_search_core.source_status)", () => {
  it("skipped_keyless wins over everything", () => {
    expect(classifySource({ ok: true, count: 5, skipped_keyless: true })).toBe(
      "keyless",
    );
  });
  it("ok with count>=0 is ok (even count 0)", () => {
    expect(classifySource({ ok: true, count: 0 })).toBe("ok");
    expect(classifySource({ ok: true, count: 12 })).toBe("ok");
  });
  it("429 / throttle / rate error => throttled", () => {
    expect(classifySource({ ok: false, error: "HTTP 429" })).toBe("throttled");
    expect(classifySource({ ok: false, error: "throttled by host" })).toBe(
      "throttled",
    );
    expect(classifySource({ ok: false, error: "rate limit" })).toBe(
      "throttled",
    );
  });
  it("key / auth / 401 / 403 error => keyless", () => {
    expect(classifySource({ ok: false, error: "missing API key" })).toBe(
      "keyless",
    );
    expect(classifySource({ ok: false, error: "401 Unauthorized" })).toBe(
      "keyless",
    );
    expect(classifySource({ ok: false, error: "403 Forbidden" })).toBe(
      "keyless",
    );
  });
  it("any other error => failed", () => {
    expect(classifySource({ ok: false, error: "connection reset" })).toBe(
      "failed",
    );
    expect(classifySource({ ok: false, error: "" })).toBe("failed");
  });
});

describe("reduceProgress", () => {
  const feed = (events: ProgressEvent[]) =>
    events.reduce(reduceProgress, emptyProgress());

  it("start sets the total", () => {
    const p = feed([{ phase: "start", total: 6 }]);
    expect(p.total).toBe(6);
    expect(p.completed).toBe(0);
    expect(p.sources).toHaveLength(0);
  });

  it("source_start appends a running row (idempotent per source)", () => {
    const p = feed([
      { phase: "start", total: 2 },
      { phase: "source_start", source: "AdzunaClient" },
      { phase: "source_start", source: "AdzunaClient" }, // dup — ignored
    ]);
    expect(p.sources).toHaveLength(1);
    expect(p.sources[0]).toMatchObject({
      source: "AdzunaClient",
      running: true,
      done: false,
      status: null,
    });
  });

  it("source_done fills the running row, sets status, bumps completed", () => {
    const p = feed([
      { phase: "start", total: 2 },
      { phase: "source_start", source: "AdzunaClient" },
      {
        phase: "source_done",
        source: "AdzunaClient",
        count: 12,
        ok: true,
        error: "",
        done: 1,
        total: 2,
      },
    ]);
    expect(p.completed).toBe(1);
    expect(p.sources[0]).toMatchObject({
      running: false,
      done: true,
      count: 12,
      status: "ok",
    });
  });

  it("a source_done with no preceding source_start still appends + counts", () => {
    const p = feed([
      { phase: "start", total: 1 },
      {
        phase: "source_done",
        source: "JoobleClient",
        count: 0,
        ok: true,
        error: "",
        done: 1,
        total: 1,
        skipped_keyless: true,
      },
    ]);
    expect(p.sources).toHaveLength(1);
    expect(p.completed).toBe(1);
    expect(p.sources[0].status).toBe("keyless");
    expect(p.sources[0].skippedKeyless).toBe(true);
  });

  it("a boundary-duplicate source_done does not double-count completed", () => {
    const doneEv: ProgressEvent = {
      phase: "source_done",
      source: "AdzunaClient",
      count: 3,
      ok: true,
      error: "",
      done: 1,
      total: 2,
    };
    const p = feed([
      { phase: "start", total: 2 },
      { phase: "source_start", source: "AdzunaClient" },
      doneEv,
      doneEv, // replayed at the SSE boundary
    ]);
    expect(p.completed).toBe(1);
    expect(p.sources).toHaveLength(1);
  });

  it("done sets finished + raw/deduped", () => {
    const p = feed([
      { phase: "start", total: 1 },
      { phase: "done", raw: 140, deduped: 95 },
    ]);
    expect(p.finished).toBe(true);
    expect(p.raw).toBe(140);
    expect(p.deduped).toBe(95);
  });

  it("does not mutate the previous state (returns a new object)", () => {
    const a = emptyProgress();
    const b = reduceProgress(a, { phase: "start", total: 3 });
    expect(a.total).toBe(0);
    expect(b.total).toBe(3);
    expect(b).not.toBe(a);
  });

  it("ignores unknown phases", () => {
    const a = feed([{ phase: "start", total: 2 }]);
    const b = reduceProgress(a, { phase: "mystery" } as ProgressEvent);
    expect(b).toEqual(a);
  });
});

describe("progressFraction", () => {
  it("is 0 when total is unknown", () => {
    expect(progressFraction(emptyProgress())).toBe(0);
  });
  it("is completed/total, clamped to [0,1]", () => {
    expect(
      progressFraction({ ...emptyProgress(), total: 4, completed: 1 }),
    ).toBe(0.25);
    expect(
      progressFraction({ ...emptyProgress(), total: 4, completed: 4 }),
    ).toBe(1);
    expect(
      progressFraction({ ...emptyProgress(), total: 4, completed: 9 }),
    ).toBe(1);
  });
});

describe("healthCounts", () => {
  it("tallies finished rows by status, ignoring running rows", () => {
    const p = [
      { phase: "start", total: 4 },
      { phase: "source_start", source: "RunningClient" }, // not done
      {
        phase: "source_done",
        source: "A",
        count: 5,
        ok: true,
        error: "",
        done: 1,
        total: 4,
      },
      {
        phase: "source_done",
        source: "B",
        count: 0,
        ok: false,
        error: "",
        done: 2,
        total: 4,
        skipped_keyless: true,
      },
      {
        phase: "source_done",
        source: "C",
        count: 0,
        ok: false,
        error: "429",
        done: 3,
        total: 4,
      },
      {
        phase: "source_done",
        source: "D",
        count: 0,
        ok: false,
        error: "boom",
        done: 4,
        total: 4,
      },
    ].reduce(reduceProgress, emptyProgress());
    expect(healthCounts(p)).toEqual({
      ok: 1,
      keyless: 1,
      throttled: 1,
      failed: 1,
    });
  });
});
