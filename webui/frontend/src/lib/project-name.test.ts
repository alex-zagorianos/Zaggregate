import { describe, it, expect } from "vitest";

import { slugify, checkProjectName } from "./project-name";

describe("slugify (mirrors workspace.slugify)", () => {
  it("lowercases and dashes non-alnum runs", () => {
    expect(slugify("Marketing Roles")).toBe("marketing-roles");
    expect(slugify("Dad's Search!!")).toBe("dad-s-search");
    expect(slugify("PROJECT a!")).toBe("project-a");
  });

  it("trims leading/trailing dashes", () => {
    expect(slugify("  spaced  ")).toBe("spaced");
    expect(slugify("--edge--")).toBe("edge");
    expect(slugify("!!!hi!!!")).toBe("hi");
  });

  it("falls back to 'project' for an all-symbol / empty name", () => {
    expect(slugify("")).toBe("project");
    expect(slugify("!!!")).toBe("project");
    expect(slugify("   ")).toBe("project");
  });
});

describe("checkProjectName", () => {
  const existing = ["project-a", "dad-search"];

  it("accepts a fresh, non-empty name", () => {
    const r = checkProjectName("Design Search", existing);
    expect(r.valid).toBe(true);
    expect(r.slug).toBe("design-search");
    expect(r.reason).toBe("");
  });

  it("rejects an empty / whitespace name", () => {
    for (const bad of ["", "   ", "\t"]) {
      const r = checkProjectName(bad, existing);
      expect(r.valid).toBe(false);
      expect(r.reason).toMatch(/name/i);
    }
  });

  it("rejects a name whose slug collides with an existing project", () => {
    // Different spelling, same slug as the existing "project-a".
    const r = checkProjectName("PROJECT a!", existing);
    expect(r.valid).toBe(false);
    expect(r.slug).toBe("project-a");
    expect(r.reason).toMatch(/already exists/i);
  });

  it("trims before deriving the slug", () => {
    const r = checkProjectName("  Design Search  ", existing);
    expect(r.valid).toBe(true);
    expect(r.slug).toBe("design-search");
  });
});
