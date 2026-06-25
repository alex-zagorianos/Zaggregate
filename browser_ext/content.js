// Job Harvester — content script
//
// Two layers of capture:
//   1. CARDS  — the search-results list. Shallow: title/company/location/url/
//      salary, plus light card signals (posting age, applicants, easy-apply,
//      promoted). One entry per visible card.
//   2. DETAIL — the job *detail* pane, captured PASSIVELY when you open a job
//      (LinkedIn/Indeed show it in a right pane without leaving the page; a full
//      /jobs/view or /viewjob page works too). This is where the real data is:
//      the full description body + a raw "details" blob (employment type, work
//      mode, seniority, applicants, posted age). We forward the body + blob and
//      let ONE server-side parser (browser_receiver.py) pull the fields out —
//      same robustness trick as salary: the JS just grabs containers, the Python
//      owns the regexes, so selector micro-churn can't silently diverge two
//      parsers. Opening a job UPGRADES its stored card in place (matched by a
//      stable external id); a job you open without ever seeing its card is added.
//
// To add a new site: add one entry to SITES (and optionally DETAIL). Selectors
// are tried in order — first match wins.

// ─────────────────────────────────────────────
//  SITES REGISTRY (results-list cards)
// ─────────────────────────────────────────────
const SITES = [
  {
    name: "linkedin",
    match: /linkedin\.com/,
    baseUrl: "https://www.linkedin.com",
    cards: [
      "li.jobs-search-results__list-item",
      "li.scaffold-layout__list-item",
      "div.job-card-container",
    ],
    titleLink: [
      "a.job-card-list__title--link",
      "a[class*='job-card-list__title']",
      ".job-card-list__title a",
      "h3 > a",
    ],
    // Verified live 2026-06-14: LinkedIn migrated to the artdeco-entity-lockup
    // card structure, so the lockup selectors lead (older ones kept as fallback).
    company: [
      ".artdeco-entity-lockup__subtitle span",
      ".job-card-container__primary-description",
      ".job-card-container__company-name",
      "h4 a",
    ],
    location: [
      ".artdeco-entity-lockup__caption li",
      "li.job-card-container__metadata-item:first-child",
      ".job-search-card__location",
    ],
    // Salary sits in a metadata <li> with a randomized class, inside the SECOND
    // of two metadata wrappers — so first() can't target it. Grab the whole
    // entity-lockup content (verified to contain it on every salaried card) and
    // let browser_receiver._parse_salary pull the $ amount out.
    salary: [
      ".artdeco-entity-lockup__content",
      ".job-card-list__salary",
      "li.job-card-container__metadata-item:nth-child(2)",
    ],
    // Light card-level signals (best-effort; all optional).
    footer: [
      ".job-card-container__footer-wrapper",
      ".job-card-list__footer-wrapper",
      "ul.job-card-container__footer-job-state",
    ],
    // The job id lives on the list item as a data attr, or in the title href.
    idAttrs: ["data-occludable-job-id", "data-job-id"],
    idUrlRe: /(?:jobs\/view\/|currentJobId=)(\d+)/,
  },
  {
    name: "indeed",
    match: /indeed\.com/,
    baseUrl: "https://www.indeed.com",
    cards: [
      "div.job_seen_beacon",
      "li[class*='JobListItem']",
      "td.resultContent",
    ],
    titleLink: ["h2.jobTitle a", "a[data-jk]", "[data-testid='jobTitle'] a"],
    company: [
      "span.companyName",
      "[data-testid='company-name']",
      ".companyInfo a",
    ],
    location: ["div.companyLocation", "[data-testid='text-location']"],
    salary: [
      ".salary-snippet-container span",
      "[data-testid='attribute_snippet_testid']",
      ".metadataContainer",
    ],
    footer: [".jobMetaDataGroup", ".result-footer", ".underShelfFooter"],
    idAttrs: ["data-jk"],
    idUrlRe: /(?:jk|vjk)=([a-z0-9]+)/i,
  },
  {
    name: "glassdoor",
    match: /glassdoor\.com/,
    baseUrl: "https://www.glassdoor.com",
    // data-test attributes are stable across React re-renders
    cards: [
      "[data-test='jobListing']",
      "li[class*='JobsList_jobListItem']",
      "li[class*='jobListItem']",
    ],
    titleLink: [
      "a[data-test='job-link']",
      "a[class*='JobCard_jobTitle']",
      "a[class*='jobTitle']",
    ],
    company: [
      "[data-test='employer-name']",
      "[class*='EmployerProfile_employerName']",
      "[class*='employerName']",
    ],
    location: [
      "[data-test='emp-location']",
      "[class*='JobCard_location']",
      "[class*='location']",
    ],
    salary: [
      "[data-test='detailSalary']",
      "[class*='SalaryEstimate_salaryRange']",
      "[class*='salaryEstimate']",
    ],
  },
  {
    name: "ziprecruiter",
    match: /ziprecruiter\.com/,
    baseUrl: "https://www.ziprecruiter.com",
    cards: [
      "article[class*='job_result']",
      "[data-job-id]",
      "article.job_content",
    ],
    titleLink: [
      "h2.job_title a",
      "a[class*='job_title']",
      "a[data-testid='job-title']",
    ],
    company: [
      ".hiring_company_text",
      "a[class*='company']",
      "[data-testid='job-employer']",
    ],
    location: [
      ".location_name",
      "[class*='location']",
      "[data-testid='job-location']",
    ],
    salary: [".job_salary", "[class*='salary']", "[data-testid='job-salary']"],
  },
  {
    name: "dice",
    match: /dice\.com/,
    baseUrl: "https://www.dice.com",
    // Dice uses custom elements (dhi-search-card) as well as data-cy attrs
    cards: [
      "dhi-search-card",
      "[data-cy='search-card']",
      "[class*='card-list-item']",
    ],
    titleLink: [
      "a[data-cy='card-title-link']",
      "a.card-title-link",
      "a[class*='title-link']",
    ],
    company: [
      "[data-cy='search-result-company-name']",
      ".company-name",
      "[class*='companyName']",
    ],
    location: [
      "[data-cy='search-result-location']",
      ".location-name",
      "[class*='location']",
    ],
    salary: ["[data-cy='card-salary']", ".salary-snippet", "[class*='salary']"],
  },
];

// ─────────────────────────────────────────────
//  DETAIL REGISTRY (open-job pane) — LinkedIn + Indeed only.
//  `pane` must be present for detail capture to run. `description` is the body.
//  `details` selectors are joined into one raw blob and parsed server-side.
// ─────────────────────────────────────────────
const DETAIL = {
  linkedin: {
    pane: [
      ".jobs-search__job-details",
      ".job-view-layout",
      ".jobs-details",
      "#job-details",
    ],
    description: [
      "#job-details",
      ".jobs-description__content .jobs-box__html-content",
      ".jobs-description-content__text",
      ".jobs-description__content",
      "article.jobs-description__container",
    ],
    // Top-card area: company line, location, "Posted…", "N applicants", and the
    // Remote/Full-time/Mid-Senior insight pills. Captured raw for server parsing.
    details: [
      ".job-details-jobs-unified-top-card__primary-description-container",
      ".job-details-jobs-unified-top-card__job-insight",
      ".jobs-unified-top-card__primary-description",
      ".jobs-unified-top-card__job-insight",
      ".job-details-jobs-unified-top-card__tertiary-description-container",
    ],
    // Apply button text reveals "Easy Apply".
    apply: [".jobs-apply-button", "button[class*='jobs-apply-button']"],
    idUrlRe: /(?:jobs\/view\/|currentJobId=)(\d+)/,
  },
  indeed: {
    pane: [
      ".jobsearch-RightPane",
      "#jobsearch-ViewjobPaneWrapper",
      ".fastviewjob",
      ".jobsearch-BodyContainer",
    ],
    description: [
      "#jobDescriptionText",
      ".jobsearch-JobComponent-description",
      "[id='jobDescriptionText']",
    ],
    details: [
      ".jobsearch-JobInfoHeader-subtitle",
      "#salaryInfoAndJobType",
      ".jobsearch-JobMetadataHeader-item",
      "[data-testid='jobsearch-JobInfoHeader-companyLocation']",
      "[class*='js-match-insights-provider']",
    ],
    apply: [
      "#indeedApplyButton",
      ".jobsearch-IndeedApplyButton-newDesign",
      "[data-testid='indeedApplyButton']",
      "button[id*='ApplyButton']",
    ],
    idUrlRe: /(?:jk|vjk)=([a-z0-9]+)/i,
  },
};

// ─────────────────────────────────────────────
//  Detect which site we're on — bail if unsupported
// ─────────────────────────────────────────────
const SITE = SITES.find((s) => s.match.test(location.hostname));
if (!SITE) {
  // Not a supported site — do nothing
  // (content script only loads on listed domains anyway)
  throw new Error("[Job Harvester] unsupported site — stopping.");
}
const SITE_DETAIL = DETAIL[SITE.name] || null;

// ─────────────────────────────────────────────
//  Helpers
// ─────────────────────────────────────────────
function first(el, selectors) {
  for (const s of selectors) {
    try {
      const found = el.querySelector(s);
      if (found) return found;
    } catch (_) {
      /* invalid selector on this site's DOM — skip */
    }
  }
  return null;
}

function firstText(el, selectors) {
  const node = first(el, selectors);
  return node ? (node.innerText || node.textContent || "").trim() : "";
}

// Join the text of every matching `details` container into one blob (deduped
// lines), so the server-side parser has all the metadata in one string.
function collectDetailsBlob(root, selectors) {
  const seen = new Set();
  const parts = [];
  for (const sel of selectors) {
    let nodes = [];
    try {
      nodes = [...root.querySelectorAll(sel)];
    } catch (_) {
      continue;
    }
    for (const n of nodes) {
      const t = (n.innerText || n.textContent || "").trim();
      if (t && !seen.has(t)) {
        seen.add(t);
        parts.push(t);
      }
    }
  }
  return parts.join("\n");
}

// Salary is parsed server-side (one implementation, in browser_receiver.py).
// We only forward the raw text so the JS and Python parsers can't diverge.
//
// But the LinkedIn salary selector grabs a whole entity-lockup blob (the salary
// <li> has a randomized class, so we can't target it directly). Forwarding that
// entire blob means a promo/bonus "$" elsewhere in the card can sit ahead of the
// real salary. So before forwarding, shrink the blob toward the salary: find the
// innermost descendant whose own text holds a "$", and forward just that. Falls
// back to the full blob's text when no "$"-bearing leaf is found.
const _MONEY_TEXT = /\$\s*\d/;

function shrinkToSalary(el) {
  if (!el) return "";
  const full = el.innerText?.trim() || "";
  if (!_MONEY_TEXT.test(full)) return full;
  // Prefer the smallest descendant that still contains a $ amount.
  let best = el;
  for (const node of el.querySelectorAll("*")) {
    const t = node.innerText?.trim() || "";
    if (
      _MONEY_TEXT.test(t) &&
      t.length < (best.innerText?.trim().length || Infinity)
    ) {
      best = node;
    }
  }
  return best.innerText?.trim() || full;
}

function resolveUrl(raw) {
  if (!raw) return "";
  if (raw.startsWith("http")) return raw.split("?")[0].replace(/\/$/, "");
  if (raw.startsWith("/"))
    return SITE.baseUrl + raw.split("?")[0].replace(/\/$/, "");
  return "";
}

// Stable per-posting id (LinkedIn numeric job id, Indeed jk). Lets a detail
// capture re-find the card it belongs to even when the URL has been normalized.
function externalIdFromCard(card, titleEl) {
  for (const attr of SITE.idAttrs || []) {
    const v = card.getAttribute?.(attr);
    if (v) return v;
    const inner = card.querySelector?.(`[${attr}]`);
    if (inner) return inner.getAttribute(attr);
  }
  if (SITE.idUrlRe) {
    const href = titleEl?.href || titleEl?.getAttribute?.("href") || "";
    const m = href.match(SITE.idUrlRe);
    if (m) return m[1];
  }
  return "";
}

function externalIdFromUrl() {
  if (SITE_DETAIL?.idUrlRe) {
    const m = location.href.match(SITE_DETAIL.idUrlRe);
    if (m) return m[1];
  }
  return "";
}

// ─────────────────────────────────────────────
//  Card extraction
// ─────────────────────────────────────────────
function extractCard(card) {
  const titleEl = first(card, SITE.titleLink);
  if (!titleEl) return null;

  // LinkedIn repeats the title in a visually-hidden span, so innerText comes
  // back as "Title\nTitle". Take the first line so it isn't captured doubled.
  const title = titleEl.innerText?.trim().split("\n")[0].trim();
  if (!title) return null;

  const url = resolveUrl(titleEl.href || titleEl.getAttribute("href") || "");
  if (!url) return null;

  const company = first(card, SITE.company)?.innerText?.trim() || "";
  const location = first(card, SITE.location)?.innerText?.trim() || "";
  const salaryTxt = shrinkToSalary(first(card, SITE.salary));
  const footerTxt = SITE.footer ? firstText(card, SITE.footer) : "";

  return {
    title,
    company,
    location,
    url,
    salary_text: salaryTxt,
    external_id: externalIdFromCard(card, titleEl),
    // Raw footer/state text ("Promoted", "Easy Apply", "3 days ago",
    // "Viewed") — parsed server-side alongside the detail blob.
    card_text: footerTxt,
    source: SITE.name,
    detailed: false,
    captured_at: new Date().toISOString(),
  };
}

// ─────────────────────────────────────────────
//  Detail extraction (the open job)
// ─────────────────────────────────────────────
function extractDetail() {
  if (!SITE_DETAIL) return null;
  const pane = first(document, SITE_DETAIL.pane);
  if (!pane) return null; // no job open

  const description = firstText(document, SITE_DETAIL.description);
  if (!description || description.length < 40) return null; // pane not loaded yet

  const detailsBlob = collectDetailsBlob(document, SITE_DETAIL.details);
  const applyTxt = firstText(document, SITE_DETAIL.apply);

  return {
    external_id: externalIdFromUrl(),
    description,
    // Combine the metadata blob + apply-button text; server parses work mode,
    // employment type, seniority, applicants, posted age, easy-apply out of it.
    details_text: [detailsBlob, applyTxt].filter(Boolean).join("\n"),
    detailed: true,
    captured_at: new Date().toISOString(),
  };
}

// ─────────────────────────────────────────────
//  Storage passes — cards add, detail upgrades-in-place
// ─────────────────────────────────────────────
// Single lock so the card pass and the detail pass can't interleave their
// read-modify-write on `jobs` (lost-update race).
let busy = false;

async function harvestCards() {
  let cards = [];
  for (const sel of SITE.cards) {
    try {
      cards = [...document.querySelectorAll(sel)];
      if (cards.length > 0) break;
    } catch (_) {}
  }
  if (cards.length === 0) return;

  const jobs = cards.map(extractCard).filter(Boolean);
  if (jobs.length === 0) return;

  const stored = await chrome.storage.local.get("jobs");
  const existing = stored.jobs || [];
  const existingUrls = new Set(existing.map((j) => j.url));

  const newJobs = jobs.filter((j) => !existingUrls.has(j.url));
  if (newJobs.length === 0) return;

  const merged = [...existing, ...newJobs];
  await chrome.storage.local.set({ jobs: merged });
  chrome.runtime.sendMessage({ type: "UPDATE_BADGE", count: merged.length });
}

async function harvestDetail() {
  const detail = extractDetail();
  if (!detail) return;

  const stored = await chrome.storage.local.get("jobs");
  const jobs = stored.jobs || [];

  // Match the open job to a stored card: prefer the stable external id, then
  // fall back to the current page URL's job path.
  const wantId = detail.external_id;
  const urlId = (location.href.match(SITE_DETAIL.idUrlRe) || [])[1] || "";
  let idx = -1;
  if (wantId)
    idx = jobs.findIndex((j) => j.external_id && j.external_id === wantId);
  if (idx === -1 && urlId)
    idx = jobs.findIndex(
      (j) => j.external_id === urlId || (j.url || "").includes(urlId),
    );

  if (idx !== -1) {
    // Don't re-write an already-detailed record with identical data (avoids a
    // storage write + badge ping on every mutation while a job stays open).
    if (jobs[idx].detailed && jobs[idx].description) return;
    jobs[idx] = { ...jobs[idx], ...detail };
    await chrome.storage.local.set({ jobs });
    chrome.runtime.sendMessage({ type: "UPDATE_BADGE", count: jobs.length });
    return;
  }

  // Opened a job whose card was never harvested (e.g. a direct /jobs/view link)
  // — add it as a standalone, detail-only record so it's still collected.
  const titleEl = first(document, [
    ".job-details-jobs-unified-top-card__job-title",
    "h2.jobsearch-JobInfoHeader-title",
    "[data-testid='jobsearch-JobInfoHeader-title']",
    "h1",
  ]);
  const title = titleEl ? (titleEl.innerText || "").trim().split("\n")[0] : "";
  if (!title) return;
  const companyEl = first(document, [
    ".job-details-jobs-unified-top-card__company-name a",
    ".job-details-jobs-unified-top-card__company-name",
    "[data-testid='inlineHeader-companyName']",
    "[data-company-name='true']",
  ]);
  jobs.push({
    title,
    company: companyEl ? (companyEl.innerText || "").trim() : "",
    location: "",
    url: resolveUrl(location.href),
    salary_text: "",
    source: SITE.name,
    card_text: "",
    ...detail,
  });
  await chrome.storage.local.set({ jobs });
  chrome.runtime.sendMessage({ type: "UPDATE_BADGE", count: jobs.length });
}

async function run() {
  if (busy) return;
  busy = true;
  try {
    await harvestCards();
    await harvestDetail();
  } finally {
    busy = false;
  }
}

// ─────────────────────────────────────────────
//  Triggers
// ─────────────────────────────────────────────
run();

// Debounced MutationObserver — avoids thrashing on every DOM change
let harvestTimer = null;
const observer = new MutationObserver(() => {
  clearTimeout(harvestTimer);
  harvestTimer = setTimeout(run, 600);
});
observer.observe(document.body, { childList: true, subtree: true });

// SPA URL change detection (LinkedIn, Glassdoor, ZipRecruiter are SPAs).
// Opening a job changes the URL (?currentJobId / ?vjk), which triggers a detail
// capture even when the DOM mutation was small.
let lastUrl = location.href;
setInterval(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    setTimeout(run, 1200);
  }
}, 1000);
