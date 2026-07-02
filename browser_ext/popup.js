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
  setStatus("Start receiver: py -m scrape.browser_receiver", "err");
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

// Init
refreshCount();
checkReceiver();
