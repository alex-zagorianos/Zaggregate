// Job Harvester — content script
// Runs on linkedin.com/jobs/* and indeed.com/*
// Collects job cards as the user browses and stores them in chrome.storage.local

const SITE = window.location.hostname.includes("linkedin") ? "linkedin" : "indeed";

// ---------- Selectors ----------
// Each is an ordered list of fallbacks — first match wins.
const SEL = {
  linkedin: {
    cards:    ["li.jobs-search-results__list-item", "li.scaffold-layout__list-item"],
    titleLink:["a.job-card-list__title--link", "a[class*='job-card-list__title']", ".job-card-list__title a", "h3 > a"],
    company:  [".job-card-container__primary-description", ".job-card-container__company-name", "h4 a", ".artdeco-entity-lockup__subtitle span"],
    location: ["li.job-card-container__metadata-item:first-child", ".job-search-card__location", ".artdeco-entity-lockup__caption li"],
    salary:   [".job-card-list__salary", "li.job-card-container__metadata-item:nth-child(2)"],
  },
  indeed: {
    cards:    ["div.job_seen_beacon", "li[class*='JobListItem']", "td.resultContent"],
    titleLink:["h2.jobTitle a", "a[data-jk]", "[data-testid='jobTitle'] a"],
    company:  ["span.companyName", "[data-testid='company-name']", ".companyInfo a"],
    location: ["div.companyLocation", "[data-testid='text-location']"],
    salary:   [".salary-snippet-container span", "[data-testid='attribute_snippet_testid']"],
  },
};

function first(el, selectors) {
  for (const s of selectors) {
    const found = el.querySelector(s);
    if (found) return found;
  }
  return null;
}

function parseSalary(text) {
  if (!text) return { min: null, max: null };
  // Match patterns like $85,000, $85K, $45/hr, $85,000 - $110,000
  const nums = [...text.matchAll(/\$[\d,]+\.?\d*[Kk]?/g)].map(m => {
    let n = m[0].replace(/[$,]/g, "");
    if (n.toLowerCase().endsWith("k")) n = parseFloat(n) * 1000;
    else n = parseFloat(n);
    // Convert hourly to annual
    if (/hr|hour/i.test(text)) n = n * 2080;
    return n;
  });
  return { min: nums[0] || null, max: nums[1] || null };
}

function extractCard(card) {
  const s = SEL[SITE];

  const titleEl = first(card, s.titleLink);
  if (!titleEl) return null;

  const title = titleEl.innerText?.trim();
  if (!title) return null;

  let url = titleEl.href || "";
  if (SITE === "linkedin" && url.startsWith("/")) {
    url = "https://www.linkedin.com" + url;
  }
  // Strip LinkedIn tracking params
  url = url.split("?")[0].replace(/\/$/, "");
  if (!url) return null;

  const company  = first(card, s.company)?.innerText?.trim() || "";
  const location = first(card, s.location)?.innerText?.trim() || "";
  const salaryEl = first(card, s.salary);
  const salaryTxt = salaryEl?.innerText?.trim() || "";
  const { min, max } = parseSalary(salaryTxt);

  return {
    title,
    company,
    location,
    url,
    salary_text: salaryTxt,
    salary_min: min,
    salary_max: max,
    source: SITE,
    captured_at: new Date().toISOString(),
  };
}

async function harvest() {
  const s = SEL[SITE];
  let cards = [];
  for (const sel of s.cards) {
    cards = [...document.querySelectorAll(sel)];
    if (cards.length > 0) break;
  }

  if (cards.length === 0) return;

  const jobs = cards.map(extractCard).filter(Boolean);
  if (jobs.length === 0) return;

  // Load existing stored jobs, merge by URL (dedup)
  const stored = await chrome.storage.local.get("jobs");
  const existing = stored.jobs || [];
  const existingUrls = new Set(existing.map(j => j.url));

  const newJobs = jobs.filter(j => !existingUrls.has(j.url));
  if (newJobs.length === 0) return;

  const merged = [...existing, ...newJobs];
  await chrome.storage.local.set({ jobs: merged });

  // Update badge via background
  chrome.runtime.sendMessage({ type: "UPDATE_BADGE", count: merged.length });
}

// Run on load
harvest();

// Re-run as new cards load (infinite scroll / pagination)
const observer = new MutationObserver(() => harvest());
observer.observe(document.body, { childList: true, subtree: true });

// Also re-run on URL changes (LinkedIn is a SPA)
let lastUrl = location.href;
setInterval(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    setTimeout(harvest, 1000); // wait for new page content
  }
}, 1000);
