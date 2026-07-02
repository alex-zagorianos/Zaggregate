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
//
// The SITES / DETAIL / RESULTS_URL_RE registries live in selectors.js (loaded
// FIRST in the manifest content_scripts `js` array), so they're already defined
// as globals here. The popup's on-demand health check injects that SAME file, so
// the harvester and the audit can't drift (that's why the old standalone
// selector_check.js needed a hand-kept "keep in sync" mirror — selectors.js
// removes the duplication).

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

// Query params that IDENTIFY a specific posting and must survive normalization
// (Indeed keeps the job id in ?jk=/?vjk=; some boards use ?currentJobId=). The
// old code stripped the whole query, collapsing every Indeed card onto a single
// dead .../viewjob URL. Tracking params are still dropped.
const ID_PARAMS = ["jk", "vjk", "currentjobid"];
function resolveUrl(raw) {
  if (!raw) return "";
  let abs = "";
  if (raw.startsWith("http")) abs = raw;
  else if (raw.startsWith("/")) abs = SITE.baseUrl + raw;
  else return "";
  try {
    const u = new URL(abs);
    const keep = [];
    for (const [k, v] of u.searchParams) {
      if (ID_PARAMS.includes(k.toLowerCase())) keep.push([k, v]);
    }
    u.search = "";
    for (const [k, v] of keep) u.searchParams.append(k, v);
    const base = (u.origin + u.pathname).replace(/\/$/, "");
    return base + (u.search || "");
  } catch (e) {
    // Malformed URL: fall back to the old strip-query behavior.
    return abs.split("?")[0].replace(/\/$/, "");
  }
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

  // Require the URL to identify WHICH job is open (currentJobId / vjk /
  // jobs/view/<id>). Without an id we can neither reliably match the open job to
  // its harvested card NOR re-find a standalone record we just pushed — so a
  // detail pane that renders before the URL settles (e.g. Indeed auto-opening
  // the first result with no vjk) would spam a fresh duplicate on every observer
  // tick. Capturing only once the job is URL-identified eliminates that and is
  // exactly "passive on the job you opened".
  const externalId = externalIdFromUrl();
  if (!externalId) return null;

  const description = firstText(document, SITE_DETAIL.description);
  if (!description || description.length < 40) return null; // pane not loaded yet

  const detailsBlob = collectDetailsBlob(document, SITE_DETAIL.details);
  const applyTxt = firstText(document, SITE_DETAIL.apply);

  return {
    external_id: externalId,
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

  // ── Selector-rot self-check (Part 3a) ────────────────────────────────────
  // Two rot signatures, evaluated only on what clearly IS a results page:
  //   1. cards selectors match >= 3 nodes but extraction yields 0 valid jobs
  //      -> the INNER selectors (title/url) have rotted.
  //   2. cards selectors match 0 nodes on a URL that IS a results page
  //      -> the CARD selectors have rotted.
  // On a page that isn't a results list (no cards, non-results URL) we say
  // nothing — that's not rot, just not the list view. reportHealth only pings
  // the worker on a TRANSITION so storage isn't rewritten every mutation tick.
  const onResultsUrl = (RESULTS_URL_RE[SITE.name] || /$^/).test(location.href);

  if (cards.length === 0) {
    if (onResultsUrl) {
      reportHealth(false, "cards: 0 nodes on a results-page URL");
    }
    return;
  }

  const jobs = cards.map(extractCard).filter(Boolean);

  if (jobs.length === 0) {
    // Cards matched but nothing extracted — inner (title/url) rot, but only
    // call it rot when there were enough cards to be confident (>= 3), so a
    // single stray element matching a card selector doesn't cry wolf.
    if (cards.length >= 3) {
      reportHealth(
        false,
        `${cards.length} cards but 0 extractable (title/url rot)`,
      );
    }
    return;
  }

  // Extraction worked — a healthy pass. Clears any prior amber for this site.
  reportHealth(true);

  const stored = await chrome.storage.local.get("jobs");
  const existing = stored.jobs || [];
  const existingUrls = new Set(existing.map((j) => j.url));

  const newJobs = jobs.filter((j) => !existingUrls.has(j.url));
  if (newJobs.length === 0) return;

  const merged = [...existing, ...newJobs];
  await chrome.storage.local.set({ jobs: merged });
  chrome.runtime.sendMessage({ type: "UPDATE_BADGE", count: merged.length });
}

// Health transitions only: remember the last state we reported for this site so
// a healthy/unhealthy verdict is sent to the worker once per change, not on
// every debounced harvest pass (which would spam storage writes).
let _lastHealthOk = null;
function reportHealth(ok, detail = "") {
  if (_lastHealthOk === ok) return; // no transition — stay quiet
  _lastHealthOk = ok;
  try {
    chrome.runtime.sendMessage({
      type: "HEALTH",
      site: SITE.name,
      ok,
      detail: ok ? "" : detail,
    });
  } catch (_) {
    /* worker asleep / context gone — non-fatal, next transition retries */
  }
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
  const standaloneUrl = resolveUrl(location.href);
  // Idempotency guard: never push a second standalone for the same job. idx===-1
  // means no card matched, but a prior standalone (or a card whose id we missed)
  // could still be present — dedup on external id OR url so a re-fire can't
  // duplicate. (extractDetail already guarantees detail.external_id is set.)
  if (
    jobs.some(
      (j) =>
        (detail.external_id && j.external_id === detail.external_id) ||
        (standaloneUrl && j.url === standaloneUrl),
    )
  ) {
    return;
  }
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
    url: standaloneUrl,
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
    await maybeAutoSend();
  } finally {
    busy = false;
  }
}

// ─────────────────────────────────────────────
//  Auto-send (Part 2) — opt-in, every 25 new jobs
// ─────────────────────────────────────────────
// When the user has turned on "Auto-send every 25 new jobs" (persisted in
// chrome.storage.local, default OFF) and the stored count crosses a fresh
// multiple of 25, ask the background worker to POST /harvest for us (with
// open_report:false so no surprise tab) and clear storage. The worker guards
// against double-fires with an in-flight flag; on receiver-down it fails
// SILENTLY — we keep collecting, the badge keeps counting, nothing is lost.
const AUTO_SEND_EVERY = 25;
// Remember the last multiple we fired at so a debounced re-run at the same count
// doesn't re-trigger. Storage-backed so it survives content-script reloads
// (SPA navigations spin up fresh content scripts).
async function maybeAutoSend() {
  let enabled = false;
  let stored;
  try {
    stored = await chrome.storage.local.get([
      "autoSend",
      "jobs",
      "autoSendLastAt",
    ]);
    enabled = stored.autoSend === true;
  } catch (_) {
    return;
  }
  if (!enabled) return;

  const count = (stored.jobs || []).length;
  const lastAt = stored.autoSendLastAt || 0;
  // Fire once per completed block of 25: the largest multiple of 25 <= count.
  const milestone = count - (count % AUTO_SEND_EVERY);
  if (milestone < AUTO_SEND_EVERY || milestone <= lastAt) return;

  // Record the milestone BEFORE messaging so a rapid second pass can't double
  // -fire; the worker's own in-flight flag is the second line of defense.
  try {
    await chrome.storage.local.set({ autoSendLastAt: milestone });
    chrome.runtime.sendMessage({ type: "AUTO_SEND" });
  } catch (_) {
    /* worker asleep / context gone — next pass retries at the next milestone */
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
