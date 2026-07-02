// Job Harvester — SITE-AGNOSTIC "Capture this job" injector.
//
// The content script (content.js) only loads on the 5 aggregator domains it has
// hand-tuned CSS selectors for. That leaves out the vast majority of real job
// pages: Workday / Greenhouse / Lever / iCIMS / SmartRecruiters tenants and
// every company careers page. This file closes that breadth gap with ZERO
// per-site selectors by reading schema.org JobPosting JSON-LD — the structured
// data Google Jobs requires, so most ATS/career pages embed it — with a
// best-effort DOM scrape as a fallback.
//
// HOW IT RUNS: popup.js calls chrome.scripting.executeScript({func:
// extractGenericJob}) on the CURRENT tab on a user gesture. activeTab +
// "scripting" let us inject into whatever tab is open with NO new host
// permissions (so no scary "read all your data on every site" install prompt).
// executeScript serializes the function by VALUE and runs it in the page's
// world, so `extractGenericJob` MUST be fully self-contained — it cannot close
// over anything in popup scope. Everything it needs is defined inside it.
//
// WHY server-parses-the-rest: we deliberately do the LEAST work here — pull the
// JSON-LD fields, strip the description HTML, compose a details_text/salary_text
// blob — and forward it in the SAME job-dict shape content.js stores. The
// receiver's ONE server-side parser (browser_receiver.py) then owns salary
// numbers, work-mode / employment-type / seniority extraction, and posting-date
// precedence. Same single-source-of-truth trick as the aggregator path: the JS
// grabs data, the Python owns the regexes, so the two capture paths can't drift.

// eslint-disable-next-line no-unused-vars  (referenced by name in popup.js)
function extractGenericJob() {
  // ── self-contained helpers (no closures over popup scope) ─────────────────

  // Strip HTML to plain text. JSON-LD `description` is almost always HTML; a
  // regex strip mangles entities and nested tags, so let the browser's own
  // parser do it. Use DOMParser (NOT innerHTML): it parses into an INERT
  // document — scripts never execute and no resources load — so untrusted
  // JSON-LD markup can't run code. We only ever read .textContent back out.
  const htmlToText = (html) => {
    if (!html) return "";
    if (typeof html !== "string") html = String(html);
    // Only pay for parsing when it actually looks like markup.
    if (!/[<&]/.test(html)) return html.trim();
    try {
      const doc = new DOMParser().parseFromString(html, "text/html");
      return (doc.body.textContent || "").replace(/\s+\n/g, "\n").trim();
    } catch (_) {
      return html.trim();
    }
  };

  // Tracking params to drop while KEEPING the path + any query that identifies
  // the posting (mirrors the spirit of content.js resolveUrl, self-contained).
  const TRACKING = new Set([
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gh_src",
    "gh_jid_source",
    "src",
    "source",
    "ref",
    "referrer",
    "trk",
    "trackingid",
    "recommended",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
  ]);
  const cleanUrl = (raw) => {
    try {
      const u = new URL(raw, location.href);
      for (const k of [...u.searchParams.keys()]) {
        if (TRACKING.has(k.toLowerCase())) u.searchParams.delete(k);
      }
      // Keep origin+path+identifying query; drop a lone trailing slash.
      const q = u.searchParams.toString();
      return (u.origin + u.pathname).replace(/\/$/, "") + (q ? "?" + q : "");
    } catch (_) {
      return raw;
    }
  };

  const metaContent = (sel) => {
    const el = document.querySelector(sel);
    const v = el && (el.getAttribute("content") || el.getAttribute("value"));
    return (v || "").trim();
  };

  // "Acme Careers" / "Careers at Acme" / "Jobs | Acme" -> "Acme".
  const stripCareerSuffix = (name) => {
    if (!name) return "";
    let s = name.trim();
    s = s.replace(/\s*[|\-–—:]\s*(careers?|jobs?|hiring|job\s*board)\s*$/i, "");
    s = s.replace(/\s+(careers?|jobs?|hiring)\s*$/i, "");
    s = s.replace(/^\s*(careers?|jobs?)\s+at\s+/i, "");
    return s.trim() || name.trim();
  };

  // schema.org @type can be a string or an array; match JobPosting either way,
  // case-insensitively (some emitters lowercase it).
  const isJobPosting = (t) => {
    if (!t) return false;
    const arr = Array.isArray(t) ? t : [t];
    return arr.some((x) => String(x).toLowerCase() === "jobposting");
  };

  // Walk one parsed JSON-LD document for the first JobPosting node: it may BE
  // the root object, sit inside a top-level array, or hang off an @graph array.
  const findJobPosting = (doc) => {
    const stack = [doc];
    while (stack.length) {
      const node = stack.pop();
      if (!node || typeof node !== "object") continue;
      if (Array.isArray(node)) {
        for (const item of node) stack.push(item);
        continue;
      }
      if (isJobPosting(node["@type"])) return node;
      if (Array.isArray(node["@graph"])) {
        for (const item of node["@graph"]) stack.push(item);
      }
    }
    return null;
  };

  // Build "City, Region" from a schema.org PostalAddress (tolerate missing
  // parts). jobLocation may be an array (multi-location) or a single object.
  const locationString = (jobLocation) => {
    const first = Array.isArray(jobLocation) ? jobLocation[0] : jobLocation;
    if (!first || typeof first !== "object") {
      return typeof first === "string" ? first.trim() : "";
    }
    const addr = first.address || first;
    if (typeof addr === "string") return addr.trim();
    const parts = [addr.addressLocality, addr.addressRegion]
      .map((p) => (p == null ? "" : String(p).trim()))
      .filter(Boolean);
    if (parts.length) return parts.join(", ");
    // Some feeds only carry a country — better than nothing.
    return (
      (addr.addressCountry &&
        (typeof addr.addressCountry === "string"
          ? addr.addressCountry
          : addr.addressCountry.name)) ||
      ""
    )
      .toString()
      .trim();
  };

  // baseSalary -> {salary_min, salary_max, salary_text}. Send numerics ONLY when
  // the unit is YEAR (the receiver stores annual floats directly); for any other
  // unit (HOUR/WEEK/MONTH) compose a salary_text like "$38.50/hour" and let the
  // server's existing hourly annualization / parsing own it — one salary parser.
  const parseSalary = (baseSalary) => {
    const out = { salary_min: null, salary_max: null, salary_text: "" };
    if (!baseSalary || typeof baseSalary !== "object") return out;
    const value = baseSalary.value;
    let minV, maxV, single, unit;
    if (value && typeof value === "object") {
      minV = value.minValue;
      maxV = value.maxValue;
      single = value.value;
      unit = value.unitText;
    } else {
      // Occasionally baseSalary.value is a bare number and the unit is a sibling.
      single = value;
      unit = baseSalary.unitText;
    }
    unit = (unit || "").toString().toUpperCase();
    const num = (x) => {
      if (x == null || x === "") return null;
      const n = parseFloat(String(x).replace(/[, ]/g, ""));
      return Number.isFinite(n) ? n : null;
    };
    const lo = num(minV != null ? minV : single);
    const hi = num(maxV);

    if (unit === "YEAR") {
      out.salary_min = lo;
      out.salary_max = hi;
      return out;
    }
    // Non-annual (or unit-less): compose text the server parses/annualizes.
    const unitWord = { HOUR: "hour", WEEK: "week", MONTH: "month", DAY: "day" }[
      unit
    ];
    const fmt = (n) => "$" + (Number.isInteger(n) ? n : n.toFixed(2));
    if (lo != null && hi != null) {
      out.salary_text = `${fmt(lo)} - ${fmt(hi)}${unitWord ? "/" + unitWord : ""}`;
    } else if (lo != null) {
      out.salary_text = `${fmt(lo)}${unitWord ? "/" + unitWord : ""}`;
    }
    return out;
  };

  // ── 1. STRUCTURED-DATA path: schema.org JobPosting JSON-LD ────────────────
  let posting = null;
  const blocks = document.querySelectorAll(
    'script[type="application/ld+json"]',
  );
  for (const s of blocks) {
    let parsed;
    try {
      parsed = JSON.parse(s.textContent);
    } catch (_) {
      continue; // tolerate a malformed block; keep scanning the others
    }
    const found = findJobPosting(parsed);
    if (found) {
      posting = found;
      break; // first JobPosting wins
    }
  }

  const now = new Date().toISOString();

  if (posting) {
    const title = (posting.title || "").toString().trim();
    const org = posting.hiringOrganization;
    const company = ((org && typeof org === "object" ? org.name : org) || "")
      .toString()
      .trim();
    const location = locationString(posting.jobLocation);
    const sal = parseSalary(posting.baseSalary);
    const description = htmlToText(posting.description);

    // Compose a details_text blob the server's parse_details already reads:
    // employmentType ("FULL_TIME" -> "Full-time"), and the Remote signal from
    // jobLocationType === "TELECOMMUTE" (or an applicantLocationRequirement).
    // datePosted is NOT parsed client-side — it rides an explicit posted_iso
    // field so the server owns the date precedence (see browser_receiver).
    const detailLines = [];
    const empType = posting.employmentType;
    const empArr = Array.isArray(empType) ? empType : empType ? [empType] : [];
    for (const e of empArr) {
      // JSON-LD uses ALLCAPS_UNDERSCORE ("FULL_TIME"); parse_details wants
      // "Full-time"/"Part-time"/"Contract"/… — normalize the common ones.
      const norm = String(e)
        .toLowerCase()
        .replace(/_/g, "-")
        .replace(/\bfull-?time\b/, "Full-time")
        .replace(/\bpart-?time\b/, "Part-time")
        .replace(/\bcontractor\b/, "Contract")
        .replace(/\btemporary\b/, "Temporary")
        .replace(/\bintern\b/, "Internship");
      if (norm) detailLines.push(norm);
    }
    const remote =
      String(posting.jobLocationType || "").toUpperCase() === "TELECOMMUTE";
    if (remote) detailLines.push("Remote");

    const job = {
      title,
      company,
      location,
      url: cleanUrl(window.location.href),
      salary_text: sal.salary_text,
      external_id: "",
      card_text: "",
      source: "page",
      detailed: !!description,
      captured_at: now,
      description,
      details_text: detailLines.join("\n"),
    };
    if (sal.salary_min != null) job.salary_min = sal.salary_min;
    if (sal.salary_max != null) job.salary_max = sal.salary_max;
    // Raw ISO datePosted -> server decides created (over capture time).
    const dp = (posting.datePosted || "").toString().trim();
    if (dp) job.posted_iso = dp;

    if (!job.title) {
      // A JobPosting with no title is unusable — fall through to DOM below.
      posting = null;
    } else {
      return { ok: true, via: "jsonld", job };
    }
  }

  // ── 2. DOM FALLBACK: best-effort when no JobPosting JSON-LD ────────────────
  // Title: first non-empty <h1>, else og:title.
  let title = "";
  for (const h of document.querySelectorAll("h1")) {
    const t = (h.innerText || h.textContent || "").trim();
    if (t) {
      title = t.split("\n")[0].trim();
      break;
    }
  }
  if (!title) title = metaContent('meta[property="og:title"]');
  title = (title || "").trim();

  // Company: og:site_name (strip " Careers"/" Jobs" chrome).
  const company = stripCareerSuffix(
    metaContent('meta[property="og:site_name"]'),
  );

  // Description: the largest visible text block. Prefer semantic containers,
  // fall back to body innerText capped so we never ship a megabyte.
  let description = "";
  const containers = [
    document.querySelector("main"),
    document.querySelector("article"),
    document.querySelector("[role=main]"),
  ].filter(Boolean);
  for (const c of containers) {
    const t = (c.innerText || c.textContent || "").trim();
    if (t.length > description.length) description = t;
  }
  if (!description) {
    description = ((document.body && document.body.innerText) || "").trim();
  }
  if (description.length > 15000) description = description.slice(0, 15000);

  if (!title && !description) {
    return { ok: false, via: "dom", job: null };
  }

  return {
    ok: true,
    via: "dom",
    job: {
      title,
      company,
      location: "",
      url: cleanUrl(window.location.href),
      salary_text: "",
      external_id: "",
      card_text: "",
      source: "page",
      detailed: !!description,
      captured_at: now,
      description,
      details_text: "",
    },
  };
}
