# Zaggregate

**A job search that works for you — on your own computer, on your side.**

Zaggregate finds jobs across roughly 20 sources at once, scores how well each
one fits _your_ preferences, and helps you apply — without ever uploading your
data or applying on your behalf. It's free, needs no account, and is built to be
used **with** the AI you already have.

## Why it's different

- **It finds jobs for you, across ~20 sources.** One search pulls from free
  public feeds (Adzuna, USAJobs, CareerOneStop / the National Labor Exchange,
  Jooble, Careerjet, The Muse, RemoteOK, Remotive, Jobicy, Himalayas,
  WeWorkRemotely, Working Nomads, Hacker News "Who is hiring?", and more) plus
  the company career pages you add across many ATS platforms (Greenhouse, Lever,
  Ashby, Workday, SmartRecruiters, Workable…). Any field — nurse, teacher,
  welder, driver, engineer — not just tech.
- **100% local and private.** No account, no cloud, no telemetry, no data sale.
  Your resume, preferences, scores, and application tracker live in a local
  folder and never leave your machine. See [PRIVACY.md](PRIVACY.md) — the whole
  policy is five lines.
- **Free, no sign-up.** There's no paywall and no account to create. Optional
  free job-source keys and your own AI make it better, but you can start with
  neither.
- **Ghost-job shielding.** Boards bury you in stale and reposted listings.
  Zaggregate flags postings that look aged or repeatedly reposted and shows an
  honest estimate of how much of your local market it can actually see — so you
  can trust the shortlist instead of guessing. It flags; it never silently hides
  your jobs.
- **Bring your own AI.** Rank and tailor with any AI chat you already use
  (Claude, ChatGPT, Gemini, Copilot — a free tier is fine), by copy-and-paste,
  no key required. Add your own API key only if you want it hands-off.
- **Assisted, never auto-apply.** Zaggregate aggregates, de-dupes, scores, and
  helps you tailor a resume and cover letter — then **you** click submit. It
  never sprays applications; mass auto-apply gets filtered out as spam and you
  stay in control.

## Why Zaggregate — own your data, apply on purpose

Every other job tool is cloud SaaS that ingests your résumé. Zaggregate is
local-first by design, and that turns two industry-wide problems into features:

- **Own your data.** A 2025 study found **90% of job platforms sell user data**
  (8 of 9 investigated sell it under CCPA; ZipRecruiter, Monster, and LinkedIn
  ranked most invasive). Zaggregate has no account, no cloud, and no telemetry —
  your résumé, preferences, scores, and tracker never leave your machine. This is
  a moat no SaaS rival can answer.
  ([inc](https://www.inc.com/bruce-crumley/90-percent-of-job-platforms-sell-user-data-study-finds-here-are-the-biggest-offenders/91358104),
  [incogni](https://blog.incogni.com/are-job-search-platforms-exploiting-job-seekers-for-their-personal-data/))
- **Assisted, not auto-apply.** Bulk auto-apply bots succeed at roughly
  **0.01% per application (1 in 10,000)** versus **4–6% for a tailored
  application** — and recruiters are actively AI-filtering the spam (Greenhouse's
  CEO calls it a hiring "doom loop"; Wonsulting shut its bulk-send feature in
  Aug 2025). Zaggregate aggregates, de-dupes, scores, and helps you tailor — then
  **you** click submit. Tailored, not sprayed.
  ([forbes](https://www.forbes.com/sites/robinryan/2025/09/22/ai-auto-apply-job-tools-recruiters-warning/),
  [cnn](https://www.cnn.com/2025/12/21/economy/ai-hiring-complication))
- **Honest reach, not ghost-job opacity.** Zaggregate tells you what fraction of
  your local market it can actually see (a "reach" badge) and flags when top
  results may be poor fits — the opposite of the outdated/ghost postings and
  résumé hallucinations reviewers hit with the auto-apply "agents."
  ([flashfire](https://www.flashfirejobs.com/blog/is-jobright-ai-legit))

## Quick start (the packaged app)

Download and unzip the release, then:

1. Open the `JobProgram` folder and run **`JobProgram.exe`**.
2. A short **Setup wizard** asks what jobs you want, where, your salary, and your
   resume — no files to edit.
3. Open your Inbox and click **Update my Inbox now**, or use the Search tab.

First time only, Windows may warn about an "unknown publisher" (the app is safe,
it just isn't code-signed yet). `JobProgram/FIRST-RUN.txt` shows the two safe
ways past it, or just double-click `JobProgram/launch.bat`.

### App modes (the same exe)

`JobProgram.exe` runs three ways — pick whichever you like:

- **`JobProgram.exe`** — the default desktop app (classic Tk window).
- **`JobProgram.exe --desktop`** — the modern web UI in a native desktop window
  (no browser needed; falls back to browser mode if the desktop runtime is
  missing).
- **`JobProgram.exe --web`** — the modern web UI in your default browser at
  `http://127.0.0.1:5002/app` (loopback only — nothing is exposed off your
  machine).

(There is also a headless `--daily` mode used by the scheduled daily update.)

## Quick start (run from source)

Requires Python 3.12 on Windows (`py -3.12`).

```
py -3.12 -m pip install -r requirements.txt
py -3.12 gui.py            # default desktop app
py -3.12 -m webui          # modern web UI in the browser
py -3.12 -m webui --desktop  # modern web UI in a native window
```

### Build the distributable exe

```
py -3.12 -m pip install pyinstaller
py -3.12 build_package.py                # -> dist/Zaggregate-v<version>.zip
py -3.12 build_package.py --production   # -> a ready-to-run production/ folder
```

The zip is a folder a friend unzips and runs with no Python install. Each built
zip ships alongside a `SHA256SUMS.txt` so a download can be verified. See
`build_package.py` for details.

## Bring your own AI (two channels)

1. **Clipboard round-trip (free, no key, any chatbot).** Click _Ask AI to rank
   these_ — it copies a ready-made prompt (your preferences + the jobs) to the
   clipboard. Paste it into any AI chat, copy the reply, and click _Paste AI
   ranking_. Each job's Fit grade lands back on the right row.
2. **MCP server (Claude Code / MCP clients).** The `claude-code/` folder ships an
   MCP server so an agent can drive search, ranking, and the application cycle
   directly. See `claude-code/` for setup.

An optional API key (Tools ▸ _Connect your AI_) enables hands-off auto-ranking
and AI resume/cover-letter drafting. Any Anthropic-compatible endpoint works
(including local Ollama, GLM, DeepSeek, Kimi via a base-URL setting).

## Architecture

The high-level map lives in [`_index.md`](_index.md); design and review notes are
under [`brain/`](brain/). Entry points: `gui.py` (desktop app), `webui/` (modern
web UI, `py -m webui`), `daily_run.py` (headless daily search → inbox),
`search/cli.py` (command line), `mcp_server.py` (MCP).

Application logs are written to `<data folder>/logs/app.log` (rotating). Use
Help ▸ _Report a problem_ to package logs + version for support — it never
includes your API keys or resume.

## Privacy & terms

- **[PRIVACY.md](PRIVACY.md)** — how your data is handled (short version: it
  stays on your computer).
- **[EULA.txt](EULA.txt)** — beta terms of use. Zaggregate is provided as-is;
  you query job sources on your own behalf and are responsible for complying
  with each source's terms.

## License

**[AGPL-3.0](LICENSE)** (GNU Affero General Public License v3.0). In plain
terms: use it, read it, modify it, share it freely — but if you distribute a
modified version, or offer a modified version to others over a network, your
modifications must be published under the same license. Your own local use is
never affected. The packaged beta additionally ships the disclaimers in
`EULA.txt` (as-is / own-behalf-querying notices of the kind AGPL §7 permits).

Contributions are accepted under AGPL-3.0 with a
[Developer Certificate of Origin](https://developercertificate.org/) sign-off
(`git commit -s`) — this keeps future licensing options (e.g. commercial
exceptions for institutions) available to the project.
