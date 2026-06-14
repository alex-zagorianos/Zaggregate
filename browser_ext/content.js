// Job Harvester — content script
//
// To add a new site: add one entry to SITES below. That's it.
// Each entry needs: match (regex on hostname), name, baseUrl,
// and selector lists for cards / titleLink / company / location / salary.
// Selectors are tried in order — first match wins.

// ─────────────────────────────────────────────
//  SITES REGISTRY
// ─────────────────────────────────────────────
const SITES = [
  {
    name: "linkedin",
    match: /linkedin\.com/,
    baseUrl: "https://www.linkedin.com",
    cards: [
      "li.jobs-search-results__list-item",
      "li.scaffold-layout__list-item",
    ],
    titleLink: [
      "a.job-card-list__title--link",
      "a[class*='job-card-list__title']",
      ".job-card-list__title a",
      "h3 > a",
    ],
    company: [
      ".job-card-container__primary-description",
      ".job-card-container__company-name",
      "h4 a",
      ".artdeco-entity-lockup__subtitle span",
    ],
    location: [
      "li.job-card-container__metadata-item:first-child",
      ".job-search-card__location",
      ".artdeco-entity-lockup__caption li",
    ],
    salary: [
      ".job-card-list__salary",
      "li.job-card-container__metadata-item:nth-child(2)",
    ],
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
    ],
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
//  Detect which site we're on — bail if unsupported
// ─────────────────────────────────────────────
const SITE = SITES.find((s) => s.match.test(location.hostname));
if (!SITE) {
  // Not a supported site — do nothing
  // (content script only loads on listed domains anyway)
  throw new Error("[Job Harvester] unsupported site — stopping.");
}

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

// Salary is parsed server-side (one implementation, in browser_receiver.py).
// We only forward the raw text so the JS and Python parsers can't diverge.

function resolveUrl(raw) {
  if (!raw) return "";
  if (raw.startsWith("http")) return raw.split("?")[0].replace(/\/$/, "");
  if (raw.startsWith("/"))
    return SITE.baseUrl + raw.split("?")[0].replace(/\/$/, "");
  return "";
}

// ─────────────────────────────────────────────
//  Card extraction
// ─────────────────────────────────────────────
function extractCard(card) {
  const titleEl = first(card, SITE.titleLink);
  if (!titleEl) return null;

  const title = titleEl.innerText?.trim();
  if (!title) return null;

  const url = resolveUrl(titleEl.href || titleEl.getAttribute("href") || "");
  if (!url) return null;

  const company = first(card, SITE.company)?.innerText?.trim() || "";
  const location = first(card, SITE.location)?.innerText?.trim() || "";
  const salaryTxt = first(card, SITE.salary)?.innerText?.trim() || "";

  return {
    title,
    company,
    location,
    url,
    salary_text: salaryTxt,
    source: SITE.name,
    captured_at: new Date().toISOString(),
  };
}

// ─────────────────────────────────────────────
//  Harvest — find cards on the current page, store new ones
// ─────────────────────────────────────────────
// Reentrancy guard: the observer + SPA timer can both fire harvest() while a
// previous run is awaiting storage. Without this, two interleaved
// read-modify-write cycles on `jobs` lose entries (lost-update race).
let harvesting = false;

async function harvest() {
  if (harvesting) return;
  harvesting = true;
  try {
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
  } finally {
    harvesting = false;
  }
}

// ─────────────────────────────────────────────
//  Triggers
// ─────────────────────────────────────────────
harvest();

// Debounced MutationObserver — avoids thrashing on every DOM change
let harvestTimer = null;
const observer = new MutationObserver(() => {
  clearTimeout(harvestTimer);
  harvestTimer = setTimeout(harvest, 600);
});
observer.observe(document.body, { childList: true, subtree: true });

// SPA URL change detection (LinkedIn, Glassdoor, ZipRecruiter are SPAs)
let lastUrl = location.href;
setInterval(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    setTimeout(harvest, 1200);
  }
}, 1000);
