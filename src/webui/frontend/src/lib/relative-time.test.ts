import { describe, it, expect } from "vitest";
import { postedLabel, relTime } from "./relative-time";

describe("postedLabel", () => {
  it("blank in → em-dash", () => {
    expect(postedLabel("")).toBe("—");
    expect(postedLabel(null)).toBe("—");
    expect(postedLabel(undefined)).toBe("—");
  });

  it("today for same-day / future timestamps", () => {
    expect(postedLabel(new Date().toISOString())).toBe("today");
  });

  it("1d for exactly one day ago", () => {
    const t = new Date(Date.now() - 25 * 3_600_000).toISOString();
    expect(postedLabel(t)).toBe("1d");
  });

  it("Nd under a month", () => {
    const t = new Date(Date.now() - 5 * 86_400_000).toISOString();
    expect(postedLabel(t)).toBe("5d");
  });

  it("Nmo at a month or more", () => {
    const t = new Date(Date.now() - 65 * 86_400_000).toISOString();
    expect(postedLabel(t)).toBe("2mo");
  });

  it("unparseable date passes through verbatim", () => {
    expect(postedLabel("not a date")).toBe("not a date");
  });
});

describe("relTime", () => {
  it("blank in → em-dash", () => {
    expect(relTime("")).toBe("—");
    expect(relTime(null)).toBe("—");
    expect(relTime(undefined)).toBe("—");
  });

  it("just now under 45s", () => {
    expect(relTime(new Date().toISOString())).toBe("just now");
  });

  it("Nm ago under an hour", () => {
    const t = new Date(Date.now() - 5 * 60_000).toISOString();
    expect(relTime(t)).toBe("5m ago");
  });

  it("Nh ago under a day", () => {
    const t = new Date(Date.now() - 3 * 3_600_000).toISOString();
    expect(relTime(t)).toBe("3h ago");
  });

  it("Nd ago under a week", () => {
    const t = new Date(Date.now() - 2 * 86_400_000).toISOString();
    expect(relTime(t)).toBe("2d ago");
  });

  it("Nw ago at a week or more", () => {
    const t = new Date(Date.now() - 14 * 86_400_000).toISOString();
    expect(relTime(t)).toBe("2w ago");
  });

  it("unparseable timestamp passes through verbatim", () => {
    expect(relTime("not a date")).toBe("not a date");
  });
});
