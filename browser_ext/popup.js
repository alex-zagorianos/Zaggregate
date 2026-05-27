const RECEIVER_URL = "http://localhost:5002";

const countEl   = document.getElementById("count");
const sendBtn   = document.getElementById("send-btn");
const clearBtn  = document.getElementById("clear-btn");
const statusEl  = document.getElementById("status");

function setStatus(msg, cls = "") {
  statusEl.textContent = msg;
  statusEl.className = cls;
}

async function refreshCount() {
  const stored = await chrome.storage.local.get("jobs");
  const jobs = stored.jobs || [];
  countEl.textContent = jobs.length;
  sendBtn.disabled = jobs.length === 0;
  if (jobs.length > 0) {
    sendBtn.textContent = `Send ${jobs.length} job${jobs.length === 1 ? "" : "s"} to Tool`;
  } else {
    sendBtn.textContent = "Send to Tool (no jobs yet)";
  }
}

async function checkReceiver() {
  try {
    const r = await fetch(`${RECEIVER_URL}/status`, { signal: AbortSignal.timeout(1000) });
    if (r.ok) {
      setStatus("Receiver running ✓", "ok");
      // Don't enable button here — refreshCount() owns disabled state based on job count
      return true;
    }
  } catch (_) {}
  setStatus("Start receiver: py -m scrape.browser_receiver", "err");
  sendBtn.disabled = true;
  return false;
}

sendBtn.addEventListener("click", async () => {
  sendBtn.disabled = true;
  setStatus("Sending…");
  const stored = await chrome.storage.local.get("jobs");
  const jobs = stored.jobs || [];
  if (jobs.length === 0) { setStatus("Nothing to send."); return; }

  try {
    const resp = await fetch(`${RECEIVER_URL}/harvest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jobs }),
    });
    const data = await resp.json();
    if (resp.ok) {
      setStatus(`Sent ${data.received} jobs — report opening in browser ✓`, "ok");
      // Clear after successful send
      await chrome.storage.local.set({ jobs: [] });
      await refreshCount();
    } else {
      setStatus(`Error: ${data.error || resp.statusText}`, "err");
      sendBtn.disabled = false;
    }
  } catch (e) {
    setStatus(`Could not reach receiver. Is it running?`, "err");
    sendBtn.disabled = false;
  }
});

clearBtn.addEventListener("click", async () => {
  await chrome.storage.local.set({ jobs: [] });
  chrome.runtime.sendMessage({ type: "UPDATE_BADGE", count: 0 });
  await refreshCount();
  setStatus("Cleared.");
});

// Init
refreshCount();
checkReceiver();
