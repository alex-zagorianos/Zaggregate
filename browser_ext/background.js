// Job Harvester — background service worker.
//
// Owns three things content scripts can't do reliably on their own:
//   1. The toolbar badge (count text + amber "!" when a site's capture looks
//      broken).
//   2. Auto-send: on the content script's signal, POST the collected jobs to the
//      receiver's /harvest (open_report:false) and clear storage — with an
//      in-flight flag so a burst of signals can't double-send.
//   3. Per-site selector-rot health, stored so the popup can surface it.

const RECEIVER_URL = "http://localhost:5002";
const NORMAL_BADGE = "#1a1a2e";
const AMBER_BADGE = "#c77700"; // capture may be broken on some site

// ── Badge ────────────────────────────────────────────────────────────────────
// The badge shows the collected count, and turns amber with a trailing "!" when
// ANY tracked site is currently unhealthy — a passive "your capture may be
// broken" signal the user sees without opening the popup.
async function refreshBadge(count) {
  if (count == null) {
    const stored = await chrome.storage.local.get("jobs");
    count = (stored.jobs || []).length;
  }
  const { health } = await chrome.storage.local.get("health");
  const anyUnhealthy =
    health && Object.values(health).some((h) => h && h.ok === false);

  let text = count > 0 ? String(count) : "";
  if (anyUnhealthy) text = text ? text + "!" : "!";
  chrome.action.setBadgeText({ text });
  chrome.action.setBadgeBackgroundColor({
    color: anyUnhealthy ? AMBER_BADGE : NORMAL_BADGE,
  });
}

// ── Auto-send (single-flight) ─────────────────────────────────────────────────
let autoSendInFlight = false;

async function doAutoSend() {
  if (autoSendInFlight) return; // guard against double-fires
  autoSendInFlight = true;
  try {
    const stored = await chrome.storage.local.get("jobs");
    const jobs = stored.jobs || [];
    if (jobs.length === 0) return;

    let resp;
    try {
      resp = await fetch(`${RECEIVER_URL}/harvest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // open_report:false — a background auto-send must never throw a report
        // tab up mid-scroll. Manual sends (popup) omit the flag -> report opens.
        body: JSON.stringify({ jobs, open_report: false }),
      });
    } catch (_) {
      // Receiver down — FAIL SILENTLY. Keep the jobs (never lose them), keep the
      // badge counting, and don't nag. The next milestone retries.
      return;
    }
    if (!resp || !resp.ok) return; // server error — keep jobs, retry later

    // Sent OK: clear storage and reset the auto-send milestone so the counter
    // restarts cleanly from 0 for the next block of 25.
    await chrome.storage.local.set({ jobs: [], autoSendLastAt: 0 });
    await refreshBadge(0);
  } finally {
    autoSendInFlight = false;
  }
}

// ── Health ────────────────────────────────────────────────────────────────────
// Store per-site health so the popup can render "capture may be broken on
// <site>" and the badge can go amber. Content scripts only send on TRANSITIONS.
async function recordHealth(site, ok, detail) {
  const { health } = await chrome.storage.local.get("health");
  const next = health || {};
  next[site] = { ok, detail: detail || "", at: Date.now() };
  await chrome.storage.local.set({ health: next });
  await refreshBadge();
}

chrome.runtime.onMessage.addListener((msg) => {
  if (!msg || !msg.type) return;
  if (msg.type === "UPDATE_BADGE") {
    refreshBadge(msg.count);
  } else if (msg.type === "AUTO_SEND") {
    doAutoSend();
  } else if (msg.type === "HEALTH") {
    recordHealth(msg.site, msg.ok, msg.detail);
  }
});
