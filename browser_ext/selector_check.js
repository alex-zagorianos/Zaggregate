// Job Harvester — selector rot self-check.
// Open a LinkedIn or Indeed JOBS SEARCH results page (the list view), open
// DevTools (F12) -> Console, paste this whole file, press Enter. It runs the
// extension's real content.js selectors against the live DOM and reports what
// still matches. Paste the output back to Claude to patch any rotted selectors.
(() => {
  const SITES = {
    linkedin: {
      match: /linkedin\.com/,
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
    indeed: {
      match: /indeed\.com/,
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
  };

  const entry = Object.entries(SITES).find(([, s]) =>
    s.match.test(location.hostname),
  );
  if (!entry) {
    console.log(
      "Not on LinkedIn/Indeed — open a jobs SEARCH results page first.",
    );
    return;
  }
  const [name, S] = entry;
  console.log(
    `%c[selector check] site=${name}  url=${location.href}`,
    "font-weight:bold;font-size:14px",
  );

  const firstSel = (sels, root = document) => {
    for (const s of sels) {
      try {
        if (root.querySelector(s)) return s;
      } catch (_) {}
    }
    return null;
  };

  let cardSel = null,
    cards = [];
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
  console.log(
    `cards: ${cards.length} matched via  ${cardSel || "NONE  <-- all card selectors rotted"}`,
  );
  if (!cards.length) {
    console.log(
      "STOP: no cards. Either not a results list, or card selectors need updating.",
    );
    return;
  }

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
  console.table(
    fields.map((f) => ({
      field: f,
      "hit %": Math.round((100 * hits[f]) / n) + "%",
      "working selector": used[f] || "NONE  <-- rotted",
    })),
  );
  console.log(
    `title (required to capture a card): ${used.titleLink ? "OK" : "MISSING -- nothing will be collected"}`,
  );
  console.log(
    `Checked ${n} of ${cards.length} cards. Copy this whole output back to Claude.`,
  );
})();
