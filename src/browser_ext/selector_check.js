// Job Harvester — selector-rot audit.
//
// Two ways to run it:
//   * ONE CLICK (normal): the popup's "Health check" button injects selectors.js
//     then THIS file into the active tab (chrome.scripting), and shows the report
//     it returns. Nothing to paste.
//   * MANUAL (console): open a LinkedIn/Indeed jobs SEARCH results page, click a
//     job so its detail pane shows, open DevTools (F12) -> Console, paste
//     selectors.js FIRST (it defines the registries), then paste THIS file. Copy
//     the printed report back to Claude to patch any rotted selectors.
//
// This file has NO selector registry of its own — it reads SITES / DETAIL from
// selectors.js, the single source of truth the live harvester (content.js) uses.
// That's the whole point: the audit can never disagree with what actually runs.
// (It used to carry a hand-kept mirror of the registries; selectors.js removed
// that drift risk.)
//
// Returns the report as a string, so chrome.scripting surfaces it as `result`
// (and a manual console paste of this IIFE shows its return value in DevTools).
(() => {
  if (typeof SITES === "undefined" || typeof DETAIL === "undefined") {
    const msg =
      "[selector check] SITES/DETAIL not found — paste selectors.js in the " +
      "console FIRST (it defines the shared selector registries), then re-run.";
    return msg;
  }

  const entry = SITES.find((s) => s.match.test(location.hostname));
  if (!entry) {
    const msg =
      "Not on a supported job site — open a jobs SEARCH results page first.";
    return msg;
  }
  const name = entry.name;
  const S = entry;
  const D = DETAIL[name] || null;

  const firstSel = (sels, root = document) => {
    for (const s of sels || []) {
      try {
        if (root.querySelector(s)) return s;
      } catch (_) {}
    }
    return null;
  };

  const out = [];
  out.push(`[selector check] site=${name}  url=${location.href}`);

  // ── CARD layer ──────────────────────────────────────────────────────────
  let cardSel = null;
  let cards = [];
  for (const s of S.cards) {
    try {
      const n = [...document.querySelectorAll(s)];
      if (n.length) {
        cardSel = s;
        cards = n;
        break;
      }
    } catch (_) {}
  }
  out.push("");
  out.push(
    `CARDS: ${cards.length} matched via ${cardSel || "NONE  <-- all card selectors rotted"}`,
  );
  if (cards.length) {
    const fields = ["titleLink", "company", "location", "salary"];
    const hits = Object.fromEntries(fields.map((f) => [f, 0]));
    const used = {};
    const sample = cards.slice(0, Math.min(cards.length, 25));
    for (const c of sample) {
      for (const f of fields) {
        const sel = firstSel(S[f], c);
        if (sel) {
          hits[f]++;
          used[f] = used[f] || sel;
        }
      }
    }
    const n = sample.length;
    for (const f of fields) {
      const pct = Math.round((100 * hits[f]) / n);
      out.push(
        `  ${f.padEnd(10)} ${String(pct).padStart(3)}%  ${used[f] || "NONE  <-- rotted"}`,
      );
    }
    out.push(
      `  title (required to capture a card): ${used.titleLink ? "OK" : "MISSING -- nothing will be collected"}`,
    );
    out.push(`  checked ${n} of ${cards.length} cards.`);
  } else {
    out.push(
      "  (No cards — open a results LIST page to audit the card layer.)",
    );
  }

  // ── DETAIL layer (needs a job open) ─────────────────────────────────────
  out.push("");
  if (!D) {
    out.push("DETAIL: (no detail registry for this site)");
  } else {
    const paneSel = firstSel(D.pane);
    out.push(
      `DETAIL pane: ${paneSel || "NONE  <-- no job open, or pane selectors rotted"}`,
    );
    if (!paneSel) {
      out.push(
        "  Click a job to open its detail pane, then re-run for the detail audit.",
      );
    } else {
      const descSel = firstSel(D.description);
      const descNode = descSel ? document.querySelector(descSel) : null;
      const descLen = descNode ? (descNode.innerText || "").trim().length : 0;
      const detailsHit = (D.details || []).filter((s) => {
        try {
          return document.querySelector(s);
        } catch (_) {
          return false;
        }
      });
      const applySel = firstSel(D.apply);
      out.push(
        `  description  ${descSel || "NONE  <-- rotted (no body captured!)"}  (${descLen} chars)`,
      );
      out.push(
        `  details      ${detailsHit[0] || "NONE  <-- rotted"}  (${detailsHit.length}/${(D.details || []).length} selectors hit)`,
      );
      out.push(
        `  apply        ${applySel || "(none)"}${
          applySel
            ? "  " +
              (document.querySelector(applySel).innerText || "")
                .trim()
                .slice(0, 40)
            : ""
        }`,
      );
      out.push(
        `  description: ${descSel && descLen > 40 ? "OK" : "MISSING/THIN -- the full body won't be captured"}`,
      );
    }
  }

  out.push("");
  out.push(
    "Copy this whole block back to Claude to patch any rotted selectors.",
  );
  const report = out.join("\n");
  return report;
})();
