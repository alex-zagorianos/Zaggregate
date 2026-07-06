# Zaggregate Beta — Getting Started

Thanks for helping test Zaggregate! It's a job-search app that runs entirely on
your own computer. It searches about 20 job sites at once, scores every job
against what _you_ said you want, and helps you keep track of your applications.
There's no account to create, nothing you type ever leaves your computer, and it
will **never apply to a job for you** — you always click Submit yourself.

## 1. Install (really just unzip)

1. Unzip the release anywhere (Desktop or Documents is fine).
2. Open the **JobProgram** folder inside.
3. Double-click **launch.bat** (easiest) — or **JobProgram.exe**.

**First time only:** Windows may show a blue "Windows protected your PC"
warning. That's just because the app isn't code-signed yet — it's safe. Click
**More info**, then **Run anyway**. (`FIRST-RUN.txt` in the same folder has
these steps written out.)

## 2. First run — the fastest setup

On first launch the app opens a short Setup wizard. The quickest way through it
is **Set up with AI**: click that button, paste the copied prompt into any AI
chat you already use (ChatGPT, Claude, Gemini, Copilot — a free tier is fine),
add your résumé plus one sentence about the work you want, and paste the reply
back. That single paste configures your whole search and starts your first one.

Prefer to type it yourself? The wizard also asks — in plain forms — what kind of
jobs you want, where (city and/or remote), your minimum salary, and (optionally)
your résumé. Answer as best you can; you can change any of it later from
**Help ▸ Run Setup Wizard**.

## 3. Everyday use

- **Inbox** is home base. Click **Update my Inbox now** and give it a few
  minutes — it's asking ~20 job sources at once. Jobs come back scored to your
  preferences, best matches first.
- **Search** lets you run a one-off search for anything, anytime.
- Click a job to see details, open it in your browser, and apply the normal
  way. The app helps you find and choose — the applying is all you.
- **Tracker**: after you apply, mark the job so you can follow it through
  applied → interview → offer.
- A "possibly stale / reposted" flag means the posting looks old or recycled —
  the app shows it anyway but is telling you to be skeptical.

## 4. Make the ranking smarter (optional, free)

Click **Ask AI to rank these**. The app copies a ready-made message to your
clipboard. Paste it into whatever AI chat you already use (ChatGPT, Claude,
Gemini, Copilot — free versions are fine), copy the AI's reply, and click
**Paste AI ranking** back in the app. Each job gets a letter "Fit" grade.

## 5. Set and forget (optional)

**Tools ▸ Turn on daily updates** — the app will quietly top up your Inbox
once a day so there's always something fresh waiting.

## Sending feedback

- If anything is broken, confusing, or slow: **Help ▸ Report a problem** makes
  a small file of logs (no résumé, no personal info). Attach it when you send
  feedback through the in-app feedback link (Help menu).
- Feedback on jobs it showed you that are obviously wrong for you, **and** good
  jobs you found elsewhere that it missed, both help a lot — send those through
  the same feedback link.

The in-app **Guide** (Help menu) is the full how-to, from first run through the
browser extension, working with AI, and ghost-job shielding.

_Prefer a more modern look? Make a shortcut to JobProgram.exe, add ` --desktop`
to the end of the shortcut's Target box, and use that instead._

_Your saved jobs, preferences, and résumé live in the `JobProgram\data` folder
— it all stays on this computer._
