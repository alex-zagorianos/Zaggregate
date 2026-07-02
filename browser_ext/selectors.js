// Job Harvester — SHARED selector registries.
//
// SINGLE SOURCE OF TRUTH for the CSS selectors both the passive content-script
// harvester (content.js) and the on-demand health check (popup.js's injected
// audit) run against the live DOM. Loaded FIRST in the manifest content_scripts
// `js` array (before content.js) so `SITES`, `DETAIL`, and `RESULTS_URL_RE`
// are already defined as globals when content.js runs; the popup injects this
// same file ahead of its audit function via chrome.scripting so the two layers
// can never drift (the previous standalone selector_check.js had to be hand-kept
// in sync — this replaces that).
//
// To add a new site: add one entry to SITES (and optionally DETAIL + a
// RESULTS_URL_RE pattern). Selectors are tried in order — first match wins.
//
// NOTE: declared with `var` (not `const`) on purpose. These run as classic
// scripts sharing one isolated-world global lexical environment: `var` puts the
// registries on the global object so content.js and the injected selector_check
// can both read them, AND makes re-injection idempotent — clicking "Health
// check" re-injects selectors.js, and a `const` re-declaration would throw
// "already declared". `var` re-declaration is a harmless no-op.

// ─────────────────────────────────────────────
//  SITES REGISTRY (results-list cards)
// ─────────────────────────────────────────────
var SITES = [
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
var DETAIL = {
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
//  RESULTS-PAGE URL patterns (per site).
//  Used by the health self-check: if the current URL clearly IS a search-results
//  page but the card selectors match 0 nodes, that's selector rot — as opposed
//  to simply not being on a results page.
// ─────────────────────────────────────────────
var RESULTS_URL_RE = {
  linkedin: /\/jobs\/search/,
  indeed: /\/jobs\b|[?&]q=/,
  glassdoor: /\/Job\//,
  ziprecruiter: /\/jobs\b|\/candidate\//,
  dice: /\/jobs\b/,
};
