import { describe, it, expect } from "vitest";
import {
  lastVisitKey,
  rowTimestamp,
  readLastVisit,
  writeLastVisit,
  countNewSince,
} from "./new-since-visit";

/** A minimal in-memory Storage stand-in for the read/write helpers. */
function memStorage(): Pick<Storage, "getItem" | "setItem"> {
  const m = new Map<string, string>();
  return {
    getItem: (k: string) => (m.has(k) ? (m.get(k) as string) : null),
    setItem: (k: string, v: string) => void m.set(k, v),
  };
}

describe("lastVisitKey", () => {
  it("keys per project slug", () => {
    expect(lastVisitKey("acme")).toBe("zg:inbox-last-visit:acme");
    expect(lastVisitKey("globex")).not.toBe(lastVisitKey("acme"));
  });

  it("falls back to a default bucket for blank/null slugs", () => {
    expect(lastVisitKey("")).toBe("zg:inbox-last-visit:default");
    expect(lastVisitKey(null)).toBe("zg:inbox-last-visit:default");
    expect(lastVisitKey(undefined)).toBe("zg:inbox-last-visit:default");
  });
});

describe("rowTimestamp", () => {
  it("prefers created, falls back to date_added", () => {
    const created = new Date("2026-07-01T00:00:00Z").getTime();
    expect(rowTimestamp({ created: "2026-07-01T00:00:00Z" })).toBe(created);
    const added = new Date("2026-06-01T00:00:00Z").getTime();
    expect(
      rowTimestamp({ created: "", date_added: "2026-06-01T00:00:00Z" }),
    ).toBe(added);
  });

  it("null when neither parses", () => {
    expect(rowTimestamp({})).toBeNull();
    expect(rowTimestamp({ created: "not a date" })).toBeNull();
  });
});

describe("read/writeLastVisit", () => {
  it("round-trips a stamp per project", () => {
    const s = memStorage();
    expect(readLastVisit("acme", s)).toBeNull();
    writeLastVisit("acme", 1000, s);
    expect(readLastVisit("acme", s)).toBe(1000);
    // A different project is independent.
    expect(readLastVisit("globex", s)).toBeNull();
  });

  it("read returns null on garbage / missing storage", () => {
    const s = memStorage();
    s.setItem("zg:inbox-last-visit:x", "not-a-number");
    expect(readLastVisit("x", s)).toBeNull();
    expect(readLastVisit("y", undefined)).toBeNull();
  });

  it("write never throws when storage is unavailable", () => {
    expect(() => writeLastVisit("z", 5, undefined)).not.toThrow();
    expect(writeLastVisit("z", 5, undefined)).toBe(5);
  });
});

describe("countNewSince", () => {
  const rows = [
    { created: "2026-07-05T00:00:00Z" }, // newest
    { created: "2026-07-02T00:00:00Z" },
    { created: "2026-06-01T00:00:00Z", date_added: "2026-06-01T00:00:00Z" },
    { created: "bad", date_added: "bad" }, // unparseable → never counted
  ];

  it("counts rows strictly newer than the stamp", () => {
    const since = new Date("2026-07-01T00:00:00Z").getTime();
    expect(countNewSince(rows, since)).toBe(2);
  });

  it("first visit (null stamp) counts nothing", () => {
    expect(countNewSince(rows, null)).toBe(0);
  });

  it("a stamp after every row counts nothing", () => {
    const since = new Date("2026-08-01T00:00:00Z").getTime();
    expect(countNewSince(rows, since)).toBe(0);
  });

  it("empty rows → 0", () => {
    expect(countNewSince([], 1000)).toBe(0);
  });
});
