const RECEIVER_URL = "http://localhost:5002";
const TRACKER_URL = "http://localhost:5001";

const countEl = document.getElementById("count");
const detailLineEl = document.getElementById("detail-line");
const hintEl = document.getElementById("hint");
const sendBtn = document.getElementById("send-btn");
const trackBtn = document.getElementById("track-btn");
const clearBtn = document.getElementById("clear-btn");
const statusEl = document.getElementById("status");
const clipBtn = document.getElementById("clip-btn");
const clipStatusEl = document.getElementById("clip-status");
const captureBtn = document.getElementById("capture-btn");
const captureStatusEl = document.getElementById("capture-status");
const verifyTabBtn = document.getElementById("verify-tab-btn");

function setStatus(msg, cls = "") {
  statusEl.textContent = msg;
  statusEl.className = cls;
}

function setClipStatus(msg, cls = "") {
  clipStatusEl.textContent = msg;
  clipStatusEl.className = cls;
}

function setCaptureStatus(msg, cls = "") {
  captureStatusEl.textContent = msg;
  captureStatusEl.className = cls;
}

async function refreshCount() {
  const stored = await chrome.storage.local.get("jobs");
  const jobs = stored.jobs || [];
  const detailed = jobs.filter((j) => j.detailed).length;
  countEl.textContent = jobs.length;
  const hasJobs = jobs.length > 0;
  trackBtn.disabled = !hasJobs;
  sendBtn.disabled = !hasJobs;

  // Surface how many carry the full description/details. If you've collected a
  // pile of cards but opened none — or detail capture has silently broken
  // (selector rot) — this stays at 0 and the hint nudges you to open jobs.
  if (hasJobs) {
    detailLineEl.textContent = `${detailed} of ${jobs.length} with full details`;
    hintEl.style.display = detailed === 0 ? "block" : "none";
    sendBtn.textContent = `Send ${jobs.length} job${jobs.length === 1 ? "" : "s"} to Tool`;
    trackBtn.textContent = `Track All as Interested (${jobs.length})`;
  } else {
    detailLineEl.textContent = "";
    hintEl.style.display = "block";
    sendBtn.textContent = "Send to Tool (no jobs yet)";
    trackBtn.textContent = "Track All as Interested";
  }
}

async function checkReceiver() {
  try {
    const r = await fetch(`${RECEIVER_URL}/status`, {
      signal: AbortSignal.timeout(1000),
    });
    if (r.ok) {
      setStatus("Receiver running ✓", "ok");
      // Clip-to-seed and generic "Capture this job" only need the receiver
      // (not already-collected jobs), so both are enabled purely on receiver
      // reachability — they work on any tab the user is looking at.
      clipBtn.disabled = false;
      captureBtn.disabled = false;
      return true;
    }
  } catch (_) {}
  setStatus("Start receiver: py -m scrape.browser_receiver", "err");
  sendBtn.disabled = true;
  clipBtn.disabled = true;
  captureBtn.disabled = true;
  return false;
}

// Send to receiver → HTML report
sendBtn.addEventListener("click", async () => {
  sendBtn.disabled = true;
  setStatus("Sending...");
  const stored = await chrome.storage.local.get("jobs");
  const jobs = stored.jobs || [];
  if (jobs.length === 0) {
    setStatus("Nothing to send.");
    return;
  }

  try {
    const resp = await fetch(`${RECEIVER_URL}/harvest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jobs }),
    });
    const data = await resp.json();
    if (resp.ok) {
      const inboxed =
        data.inboxed != null ? `, ${data.inboxed} new to inbox` : "";
      setStatus(
        `Sent ${data.received} jobs${inboxed} - report opening in browser`,
        "ok",
      );
      await chrome.storage.local.set({ jobs: [] });
      chrome.runtime.sendMessage({ type: "UPDATE_BADGE", count: 0 });
      await refreshCount();
    } else {
      setStatus(`Error: ${data.error || resp.statusText}`, "err");
      sendBtn.disabled = false;
    }
  } catch (e) {
    setStatus("Could not reach receiver. Is it running?", "err");
    sendBtn.disabled = false;
  }
});

// Track all jobs directly in the tracker as "interested"
trackBtn.addEventListener("click", async () => {
  trackBtn.disabled = true;
  setStatus("Adding to tracker...");
  const stored = await chrome.storage.local.get("jobs");
  const jobs = stored.jobs || [];
  if (jobs.length === 0) {
    setStatus("Nothing to track.");
    return;
  }

  let added = 0;
  let failed = 0;
  for (const job of jobs) {
    try {
      const resp = await fetch(`${TRACKER_URL}/api/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: job.title,
          company: job.company,
          location: job.location || "",
          url: job.url || "",
          salary_text: job.salary_text || "",
          source: job.source || "browser",
          status: "interested",
        }),
      });
      if (resp.ok) added++;
      else failed++;
    } catch (_) {
      failed++;
    }
  }

  if (failed === 0) {
    setStatus(`${added} jobs added to tracker`, "ok");
    await chrome.storage.local.set({ jobs: [] });
    chrome.runtime.sendMessage({ type: "UPDATE_BADGE", count: 0 });
    await refreshCount();
  } else if (added > 0) {
    setStatus(`${added} added, ${failed} failed - is tracker running?`, "err");
    trackBtn.disabled = false;
  } else {
    setStatus("Could not reach tracker. Start it: py -m tracker.app", "err");
    trackBtn.disabled = false;
  }
});

clearBtn.addEventListener("click", async () => {
  await chrome.storage.local.set({ jobs: [] });
  chrome.runtime.sendMessage({ type: "UPDATE_BADGE", count: 0 });
  await refreshCount();
  setStatus("Cleared.");
});

// Clip-to-seed: add the CURRENT tab's careers board to the registry. All the
// real work (resolve board root, probe live, P0-6 gate, dedup, industry tag)
// is server-side; the JS just forwards the active tab's URL + title and renders
// the verdict. Assisted, never auto — this only ADDS A BOARD to the registry.
function renderClipVerdict(v) {
  const company = v.company || "this board";
  // Any non-unreachable verdict clears the two-step verify offer.
  verifyTabBtn.style.display = "none";
  if (v.status === "added" && v.browser_only) {
    // S33 browser-verified: saved, but the app can't read this board itself.
    const cnt = v.live_count != null ? ` (${v.live_count} open jobs)` : "";
    setClipStatus(
      `Added ${company} (browser-verified)${cnt} — the app can't read this ` +
        "board itself; revisit it with the extension to refresh jobs.",
      "ok",
    );
  } else if (v.status === "added") {
    const cnt = v.live_count != null ? ` (${v.live_count} open jobs)` : "";
    const tag = v.industry ? ` — tagged "${v.industry}"` : "";
    setClipStatus(`Added ${company} — ${v.ats_type}${cnt}${tag}`, "ok");
  } else if (v.status === "duplicate") {
    setClipStatus(`Already in your registry: ${company}`, "ok");
  } else if (v.reason === "unreachable") {
    // Don't dead-end: the server couldn't read this (often a Cloudflare/CSRF-
    // walled Workday tenant), but the user's logged-in browser may be on a live
    // board. Offer the two-step "Verify from this tab" (assisted, never auto).
    setClipStatus(
      `The app couldn't read ${company} (${v.ats_type}) from here — it may be ` +
        "behind a login/anti-bot wall. If you can see its jobs on this page, " +
        "verify it from your browser:",
      "err",
    );
    verifyTabBtn.style.display = "block";
  } else {
    // unresolvable / junk / off-board
    setClipStatus(
      "This page isn't a recognized live job board — open the employer's " +
        "actual careers/ATS page, then try again.",
      "err",
    );
  }
}

// Injected into the active tab (S33). Counts job postings the user's logged-in
// browser can see so a walled board can be browser-verified. HONEST-by-contract:
// prefer schema.org/JobPosting JSON-LD (what Google for Jobs reads); else a
// conservative DOM heuristic (repeated links whose href looks like a job/req/
// posting detail); return job_count=null when neither is confident rather than
// guessing. Runs in the PAGE, so it must be fully self-contained (no closure
// over popup vars). Returns {job_count, via, page_url}.
function countJobPostingsInPage() {
  const pageUrl = location.href;

  // 1) JSON-LD JobPosting — the authoritative signal.
  let jsonldCount = 0;
  try {
    const scripts = document.querySelectorAll(
      'script[type="application/ld+json"]',
    );
    for (const s of scripts) {
      let data;
      try {
        data = JSON.parse(s.textContent);
      } catch (_) {
        continue;
      }
      const stack = Array.isArray(data) ? data.slice() : [data];
      while (stack.length) {
        const node = stack.pop();
        if (!node || typeof node !== "object") continue;
        const t = node["@type"];
        const isJob =
          t === "JobPosting" || (Array.isArray(t) && t.includes("JobPosting"));
        if (isJob) jsonldCount++;
        // @graph / itemListElement wrappers hold the real postings.
        if (Array.isArray(node["@graph"])) stack.push(...node["@graph"]);
        if (Array.isArray(node.itemListElement))
          stack.push(...node.itemListElement);
        if (node.item && typeof node.item === "object") stack.push(node.item);
      }
    }
  } catch (_) {}
  if (jsonldCount > 0) {
    return { job_count: jsonldCount, via: "jsonld", page_url: pageUrl };
  }

  // 2) DOM heuristic — repeated links to a job/requisition detail. Kept honest:
  // require several matches and de-dupe by href so a single templated link or a
  // nav menu can't fabricate a count.
  try {
    const hrefRe =
      /\/(job|jobs|requisition|req|posting|opening|career)s?[/?-]/i;
    const seen = new Set();
    document.querySelectorAll("a[href]").forEach((a) => {
      const href = a.getAttribute("href") || "";
      const text = (a.textContent || "").trim();
      // A real posting link has visible title text and a detail-ish href.
      if (text.length >= 4 && hrefRe.test(href)) seen.add(href.split("#")[0]);
    });
    if (seen.size >= 3) {
      return { job_count: seen.size, via: "dom", page_url: pageUrl };
    }
  } catch (_) {}

  // Couldn't confidently count — but the user chose to verify, so report the
  // page as live evidence with an unknown count (job_count null is accepted).
  return { job_count: null, via: "dom", page_url: pageUrl };
}

clipBtn.addEventListener("click", async () => {
  clipBtn.disabled = true;
  setClipStatus("Checking this page…");
  let tab;
  try {
    [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  } catch (_) {}
  if (!tab || !tab.url) {
    setClipStatus("Couldn't read the current tab.", "err");
    clipBtn.disabled = false;
    return;
  }
  try {
    const resp = await fetch(`${RECEIVER_URL}/clip`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: tab.url, page_title: tab.title || "" }),
    });
    const v = await resp.json();
    if (resp.ok) {
      renderClipVerdict(v);
    } else {
      setClipStatus(`Error: ${v.error || resp.statusText}`, "err");
    }
  } catch (_) {
    setClipStatus("Could not reach receiver. Is it running?", "err");
  }
  clipBtn.disabled = false;
});

// Generic "Capture this job" — works on ANY tab, not just the 5 aggregator
// domains content.js is wired for. We inject extractGenericJob (generic_capture
// .js) into the CURRENT tab on this user gesture; activeTab + "scripting" grant
// that with NO host permissions, so the install prompt stays narrow. The
// injected fn returns {ok, via, job}; we store the job here (same shape + dedup
// as content.js) and render a verdict. The heavy lifting (structured-data vs DOM
// fallback) is all in the injected function; this handler just persists + tells
// the user which path was used.
async function storeCapturedJob(job) {
  // Dedup exactly like content.js: match on url, or a shared external_id. A
  // repeat capture of the same page is a no-op (returns false); a new page adds.
  const stored = await chrome.storage.local.get("jobs");
  const jobs = stored.jobs || [];
  const dup = jobs.some(
    (j) =>
      (job.url && j.url === job.url) ||
      (job.external_id && j.external_id && j.external_id === job.external_id),
  );
  if (dup) return { added: false, total: jobs.length };
  jobs.push(job);
  await chrome.storage.local.set({ jobs });
  chrome.runtime.sendMessage({ type: "UPDATE_BADGE", count: jobs.length });
  return { added: true, total: jobs.length };
}

captureBtn.addEventListener("click", async () => {
  captureBtn.disabled = true;
  setCaptureStatus("Reading this page…");
  let tab;
  try {
    [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  } catch (_) {}
  if (!tab || tab.id == null) {
    setCaptureStatus("Couldn't read the current tab.", "err");
    captureBtn.disabled = false;
    return;
  }

  let result;
  try {
    // executeScript returns one InjectionResult per frame; we target the top
    // frame (default) so there's exactly one. func is serialized by value and
    // runs in the page world — extractGenericJob is self-contained for that.
    const injected = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractGenericJob,
    });
    result = injected && injected[0] && injected[0].result;
  } catch (e) {
    // Restricted pages (chrome://, the Chrome Web Store, PDF viewer, other
    // extensions) block injection — surface a friendly reason, not a stack.
    setCaptureStatus(
      "Can't capture from this page (it's a browser or store page). " +
        "Open the actual job posting and try again.",
      "err",
    );
    captureBtn.disabled = false;
    return;
  }

  if (!result || !result.ok || !result.job) {
    setCaptureStatus("Couldn't find a job posting here.", "err");
    captureBtn.disabled = false;
    return;
  }

  const { added } = await storeCapturedJob(result.job);
  await refreshCount();
  if (result.via === "jsonld") {
    setCaptureStatus(
      added ? "Captured via structured data ✓" : "Already collected ✓",
      "ok",
    );
  } else {
    setCaptureStatus(
      added
        ? "Captured (best-effort) — no structured data on this page"
        : "Already collected ✓",
      "ok",
    );
  }
  captureBtn.disabled = false;
});

// S33 two-step: the server couldn't read this board, but the user can see its
// jobs. Count postings in the active tab (JSON-LD first, DOM fallback) and
// re-clip WITH that evidence so it's saved browser-verified (kept out of server
// scraping; refreshed by browsing). Assisted, never auto — one explicit click.
verifyTabBtn.addEventListener("click", async () => {
  verifyTabBtn.disabled = true;
  setClipStatus("Counting jobs on this page…");
  let tab;
  try {
    [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  } catch (_) {}
  if (!tab || !tab.id || !tab.url) {
    setClipStatus("Couldn't read the current tab.", "err");
    verifyTabBtn.disabled = false;
    return;
  }

  // Inject the counting function into the page and read its evidence back.
  let evidence;
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: countJobPostingsInPage,
    });
    evidence = result && result.result;
  } catch (_) {
    // e.g. a restricted page (chrome://, the Web Store) the extension can't
    // script. Nothing to verify from here.
    setClipStatus(
      "Couldn't read this page's contents to verify it. Open the employer's " +
        "job board in a normal tab and try again.",
      "err",
    );
    verifyTabBtn.disabled = false;
    return;
  }
  if (!evidence) {
    setClipStatus("Couldn't find any jobs on this page to verify.", "err");
    verifyTabBtn.disabled = false;
    return;
  }

  // Re-clip with the browser evidence. The server saves it browser-verified
  // only if its OWN probe still can't reach the board (server probe wins).
  try {
    const resp = await fetch(`${RECEIVER_URL}/clip`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: tab.url,
        page_title: tab.title || "",
        evidence,
      }),
    });
    const v = await resp.json();
    if (resp.ok) {
      renderClipVerdict(v);
    } else {
      setClipStatus(`Error: ${v.error || resp.statusText}`, "err");
      verifyTabBtn.disabled = false;
      return;
    }
  } catch (_) {
    setClipStatus("Could not reach receiver. Is it running?", "err");
    verifyTabBtn.disabled = false;
    return;
  }
  verifyTabBtn.disabled = false;
});

// Init
refreshCount();
checkReceiver();
