# Privacy

Zaggregate runs entirely on your computer. Your resume, applications, and job
data never leave your machine. No account, no telemetry, no data sale — there's
nothing to sell. The only network calls are the job-source fetches you configure
and an optional update check against GitHub. AI features work by you copying a
prompt into the AI you already use.

That's the whole policy. The rest of this page just spells out the details in
plain language.

## What data there is, and where it lives

Everything Zaggregate stores stays in one local data folder on your computer.
You can open it any time from **Help → Open my data folder** (on a protected
install it lives under `%LOCALAPPDATA%\JobProgram`). That folder holds:

- **Your resume and preferences** — the experience text and search preferences
  you enter in the setup wizard.
- **Your job inbox and scores** — the postings pulled from your sources and the
  0–100 match score computed for each, on your machine.
- **Your application tracker** — a local SQLite database (`tracker.db`) of the
  jobs you're tracking and their status.
- **Your settings and any API keys** — if you choose to add job-source or AI
  keys, they're saved here (in plain text, like any `.env` file), only on your
  computer.

Nothing in that folder is uploaded, synced to a cloud, or sent to us. We don't
have a server, an account system, or a copy of your data — by design.

## The network calls Zaggregate makes

Zaggregate is not a cloud app, but it does reach out over the internet in a few
specific, user-controlled ways:

- **Job-source fetches you configure.** To find jobs, the app queries the public
  job sources you turn on (Adzuna, CareerOneStop, USAJobs, and the other free
  feeds), plus the company career pages you add. Each fetch runs from your
  computer, on your behalf, using your own free keys — the same requests your
  browser would make visiting those sites.
- **An optional update check.** If you use **Settings → Check for updates**, the
  app makes a single request to GitHub's public releases API to compare your
  version against the latest release. It sends no personal data — just the
  standard request GitHub sees from any download. You can ignore this feature
  and nothing ever calls out for updates.
- **The AI you already use (only if you ask).** The clipboard AI ranking is
  copy-and-paste: the app never contacts an AI itself — _you_ paste a prompt
  into your own chat. If you opt into the hands-off AI features by adding your
  own API key, the job text and your profile go to _your_ AI provider under
  _your_ key — never through us.

## The browser extension talks only to your own computer

The optional "Job Harvester" browser extension sends the jobs it captures to a
small listener running on `127.0.0.1` (localhost) — your own machine — and only
while Zaggregate is open. It never sends anything to us or to any external
server, and "Capture this job" reads only the single page you're on, only when
you click it.

## No telemetry, no analytics, no accounts

There is no usage tracking, no crash phone-home, no analytics SDK, and no sign-
up. If you want to report a bug, you do it deliberately: **Help → Report a
problem** packages logs and your version into a zip _you_ choose to send — and
it never includes your API keys or resume.

## Contact

Questions about privacy? Email **alexzagorianos@gmail.com**.

_Zaggregate is beta software provided as-is; this page describes how it handles
your data and is not legal advice. See `EULA.txt` for the terms of use._
