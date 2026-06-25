// Job Harvester — selector rot self-check.
// Open a LinkedIn or Indeed JOBS SEARCH results page (the list view), THEN
// click a job so its detail pane is showing. Open DevTools (F12) -> Console,
// paste this whole file, press Enter. It runs the extension's real content.js
// selectors (both the CARD list layer and the DETAIL pane layer) against the
// live DOM and reports what still matches. Paste the output back to Claude to
// patch any rotted selectors.
(() => {
  const SITES = {
    linkedin: {
      match: /linkedin\.com/,
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
      salary: [
        ".artdeco-entity-lockup__content",
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
        ".metadataContainer",
      ],
    },
  };

  // Mirror of content.js DETAIL — keep these two in sync when patching.
  const DETAIL = {
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
      details: [
        ".job-details-jobs-unified-top-card__primary-description-container",
        ".job-details-jobs-unified-top-card__job-insight",
        ".jobs-unified-top-card__primary-description",
        ".jobs-unified-top-card__job-insight",
        ".job-details-jobs-unified-top-card__tertiary-description-container",
      ],
      apply: [".jobs-apply-button", "button[class*='jobs-apply-button']"],
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

  // ── CARD layer ──────────────────────────────────────────────────────────
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
    `%cCARDS: ${cards.length} matched via  ${cardSel || "NONE  <-- all card selectors rotted"}`,
    "font-weight:bold",
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
    console.log(`Checked ${n} of ${cards.length} cards.`);
  } else {
    console.log(
      "(No cards — open a results LIST page to audit the card layer.)",
    );
  }

  // ── DETAIL layer (needs a job open) ─────────────────────────────────────
  const D = DETAIL[name];
  const paneSel = firstSel(D.pane);
  console.log(
    `%cDETAIL pane: ${paneSel || "NONE  <-- no job open, or pane selectors rotted"}`,
    "font-weight:bold",
  );
  if (!paneSel) {
    console.log(
      "Click a job to open its detail pane, then re-run for the detail audit.",
    );
  } else {
    const descSel = firstSel(D.description);
    const descNode = descSel ? document.querySelector(descSel) : null;
    const descLen = descNode ? (descNode.innerText || "").trim().length : 0;
    const detailsHit = D.details.filter((s) => {
      try {
        return document.querySelector(s);
      } catch (_) {
        return false;
      }
    });
    const applySel = firstSel(D.apply);
    console.table([
      {
        field: "description",
        "working selector": descSel || "NONE  <-- rotted (no body captured!)",
        info: `${descLen} chars`,
      },
      {
        field: "details(blob)",
        "working selector": detailsHit[0] || "NONE  <-- rotted",
        info: `${detailsHit.length}/${D.details.length} selectors hit`,
      },
      {
        field: "apply",
        "working selector": applySel || "(none)",
        info: applySel
          ? (document.querySelector(applySel).innerText || "")
              .trim()
              .slice(0, 40)
          : "",
      },
    ]);
    console.log(
      `description: ${descSel && descLen > 40 ? "OK" : "MISSING/THIN -- the full body won't be captured"}`,
    );
  }

  console.log(
    "%cCopy this whole output back to Claude to patch any rotted selectors.",
    "font-style:italic",
  );
})();
