import { describe, it, expect } from "vitest";
import {
  emptyForm,
  formFromJob,
  showOffer,
  dirtyFields,
  createBody,
  isDirty,
} from "./app-fields";

describe("emptyForm", () => {
  it("defaults status to interested (tk add-mode default)", () => {
    expect(emptyForm().status).toBe("interested");
    expect(emptyForm().title).toBe("");
  });
});

describe("formFromJob", () => {
  it("coerces null/undefined columns to empty strings", () => {
    const f = formFromJob({
      title: "SRE",
      company: "Acme",
      location: null,
      salary_text: undefined,
      date_applied: "2026-07-01",
    });
    expect(f.title).toBe("SRE");
    expect(f.location).toBe("");
    expect(f.salary_text).toBe("");
    expect(f.date_applied).toBe("2026-07-01");
  });
  it("falls back to interested when status is blank", () => {
    expect(formFromJob({ status: "" }).status).toBe("interested");
    expect(formFromJob({ status: "offer" }).status).toBe("offer");
  });
});

describe("showOffer", () => {
  it("shows offer fields only for offer/accepted", () => {
    expect(showOffer("offer")).toBe(true);
    expect(showOffer("accepted")).toBe(true);
    expect(showOffer("interested")).toBe(false);
    expect(showOffer("rejected")).toBe(false);
  });
});

describe("dirtyFields", () => {
  it("returns only changed fields, trimmed", () => {
    const orig = formFromJob({
      title: "SRE",
      company: "Acme",
      location: "NYC",
    });
    const cur = { ...orig, location: "  Remote  ", notes: "hi" };
    expect(dirtyFields(orig, cur)).toEqual({ location: "Remote", notes: "hi" });
  });
  it("is empty when nothing changed (no-op save)", () => {
    const orig = formFromJob({ title: "SRE", company: "Acme" });
    expect(dirtyFields(orig, { ...orig })).toEqual({});
  });
  it("ignores whitespace-only diffs", () => {
    const orig = formFromJob({ title: "SRE", company: "Acme" });
    const cur = { ...orig, title: "  SRE  " };
    expect(dirtyFields(orig, cur)).toEqual({});
  });
});

describe("createBody", () => {
  it("sends only non-empty create fields + status", () => {
    const f = emptyForm();
    f.title = "SRE";
    f.company = "Acme";
    f.url = "";
    expect(createBody(f)).toEqual({
      title: "SRE",
      company: "Acme",
      status: "interested",
    });
  });
});

describe("isDirty", () => {
  it("is true once any tracked field changes", () => {
    const orig = emptyForm();
    expect(isDirty(orig, orig)).toBe(false);
    expect(isDirty(orig, { ...orig, title: "SRE" })).toBe(true);
  });
});
