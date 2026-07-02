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
const autoSendToggle = document.getElementById("autosend-toggle");
const healthWarnEl = document.getElementById("health-warn");
const healthBtn = document.getElementById("health-btn");
const healthOutEl = document.getElementById("health-out");

function setStatus(msg, cls = "") {
  statusEl.textContent = msg;
  statusEl.className = cls;
}

function setClipStatus(msg, cls = "") {
  clipStatusEl.textContent = msg;
  clipStatusEl.className = cls;
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
      // Clip-to-seed only needs the receiver (not collected jobs), so it's
      // enabled purely on receiver reachability.
      clipBtn.disabled = false;
      return true;
    }
  } catch (_) {}
  // A general user never runs `py -m scrape.browser_receiver` — the receiver is
  // embedded in the desktop app. Point them at the real toggle; keep the CLI as
  // a secondary parenthetical for anyone running the standalone process.
  setStatus(
    "Open Zaggregate → Tools → Capture jobs from my browser… " +
      "(or run: py -m scrape.browser_receiver)",
    "err",
  );
  sendBtn.disabled = true;
  clipBtn.disabled = true;
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
      await chrome.storage.local.set({ jobs: [], autoSendLastAt: 0 });
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

// Track all collected jobs as "interested". Single-port story: try the
// receiver's /track first (the embedded receiver a general user already has ON),
// and only fall back to the legacy per-job 5001 tracker.app loop if the receiver
// isn't reachable — so nothing regresses for anyone still running tracker.app.
async function trackViaReceiver(jobs) {
  // Returns {added, failed} on success, or null if the receiver is unreachable
  // (so the caller can fall back). A non-OK HTTP response is a real error, not
  // "unreachable", so it does NOT trigger the fallback.
  try {
    const resp = await fetch(`${RECEIVER_URL}/track`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jobs }),
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.error || resp.statusText);
    }
    return await resp.json();
  } catch (e) {
    // Connection failure (receiver down) -> signal fallback. Distinguish a
    // network error (TypeError from fetch) from an HTTP error we threw above.
    if (e instanceof TypeError) return null;
    throw e;
  }
}

async function trackViaTrackerApp(jobs) {
  // Legacy path: per-job POST to tracker.app on port 5001.
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
  return { added, failed };
}

trackBtn.addEventListener("click", async () => {
  trackBtn.disabled = true;
  setStatus("Adding to tracker...");
  const stored = await chrome.storage.local.get("jobs");
  const jobs = stored.jobs || [];
  if (jobs.length === 0) {
    setStatus("Nothing to track.");
    trackBtn.disabled = false;
    return;
  }

  let result;
  try {
    result = await trackViaReceiver(jobs);
    if (result === null) {
      // Receiver down — fall back to the standalone tracker.app loop.
      result = await trackViaTrackerApp(jobs);
    }
  } catch (e) {
    setStatus(`Error adding to tracker: ${e.message}`, "err");
    trackBtn.disabled = false;
    return;
  }

  const { added, failed } = result;
  if (failed === 0 && added > 0) {
    setStatus(`${added} jobs added to tracker`, "ok");
    await chrome.storage.local.set({ jobs: [], autoSendLastAt: 0 });
    chrome.runtime.sendMessage({ type: "UPDATE_BADGE", count: 0 });
    await refreshCount();
  } else if (added > 0) {
    setStatus(`${added} added, ${failed} failed`, "err");
    trackBtn.disabled = false;
  } else {
    setStatus(
      "Could not add to tracker. Turn on Zaggregate → Tools → " +
        "Capture jobs from my browser… (or run: py -m tracker.app)",
      "err",
    );
    trackBtn.disabled = false;
  }
});

clearBtn.addEventListener("click", async () => {
  await chrome.storage.local.set({ jobs: [], autoSendLastAt: 0 });
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
  if (v.status === "added") {
    const cnt = v.live_count != null ? ` (${v.live_count} open jobs)` : "";
    const tag = v.industry ? ` — tagged "${v.industry}"` : "";
    setClipStatus(`Added ${company} — ${v.ats_type}${cnt}${tag}`, "ok");
  } else if (v.status === "duplicate") {
    setClipStatus(`Already in your registry: ${company}`, "ok");
  } else if (v.reason === "unreachable") {
    setClipStatus(
      `Couldn't verify ${company} (${v.ats_type}) as live — not added.`,
      "err",
    );
  } else {
    // unresolvable / junk / off-board
    setClipStatus(
      "This page isn't a recognized live job board — open the employer's " +
        "actual careers/ATS page, then try again.",
      "err",
    );
  }
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

// ─────────────────────────────────────────────
//  Auto-send toggle (Part 2) — persisted, default OFF
// ─────────────────────────────────────────────
async function loadAutoSend() {
  const { autoSend } = await chrome.storage.local.get("autoSend");
  autoSendToggle.checked = autoSend === true;
}

autoSendToggle.addEventListener("change", async () => {
  await chrome.storage.local.set({ autoSend: autoSendToggle.checked });
  // Re-baseline the milestone to the current count when turning ON, so flipping
  // it on with a pile already collected doesn't instantly fire for a block that
  // was gathered before the user opted in.
  if (autoSendToggle.checked) {
    const stored = await chrome.storage.local.get("jobs");
    const count = (stored.jobs || []).length;
    await chrome.storage.local.set({ autoSendLastAt: count - (count % 25) });
  }
});

// ─────────────────────────────────────────────
//  Selector-rot health (Part 3b)
// ─────────────────────────────────────────────
// If the background worker has flagged a site's capture as broken, warn here and
// offer a one-click health check. The check injects the SHARED selector registry
// (selectors.js) plus an audit function into the active tab and renders per-layer
// pass/fail counts the user can copy to Claude to get selectors patched.
async function renderHealthWarning() {
  const { health } = await chrome.storage.local.get("health");
  const broken = health
    ? Object.entries(health).filter(([, h]) => h && h.ok === false)
    : [];
  if (broken.length === 0) {
    healthWarnEl.style.display = "none";
    healthBtn.style.display = "none";
    return;
  }
  const sites = broken.map(([site]) => site).join(", ");
  healthWarnEl.textContent = `Capture may be broken on ${sites} — run the health check.`;
  healthWarnEl.style.display = "block";
  healthBtn.style.display = "block";
}

healthBtn.addEventListener("click", async () => {
  healthBtn.disabled = true;
  healthOutEl.style.display = "block";
  healthOutEl.textContent = "Running health check on the active tab…";
  let tab;
  try {
    [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  } catch (_) {}
  if (!tab || !tab.id) {
    healthOutEl.textContent = "Couldn't read the current tab.";
    healthBtn.disabled = false;
    return;
  }
  try {
    // Inject the SHARED selector registry (selectors.js) then the audit
    // (selector_check.js) as two files, in order, into the active tab's isolated
    // world. selectors.js defines SITES/DETAIL; selector_check.js's IIFE reads
    // those SAME globals (no duplicated registry -> no drift with the harvester)
    // and RETURNS the report string, which executeScript surfaces as `result`.
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["selectors.js", "selector_check.js"],
    });
    // The last injected file's completion value is the last result entry.
    const report =
      results && results.length ? results[results.length - 1].result : null;
    healthOutEl.textContent =
      report ||
      "Health check produced no output. Open a jobs SEARCH results page (LinkedIn/Indeed) and try again.";
  } catch (e) {
    healthOutEl.textContent =
      "Couldn't run the health check on this tab. Open a LinkedIn/Indeed jobs " +
      "search page — the extension can't audit chrome:// or web-store pages.\n\n" +
      (e && e.message ? e.message : "");
  }
  healthBtn.disabled = false;
});

// React to background health updates while the popup is open.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.health) renderHealthWarning();
});

// Init
refreshCount();
checkReceiver();
loadAutoSend();
renderHealthWarning();
