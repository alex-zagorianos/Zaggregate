# Design — Local-IMAP application-status detection (S38, awaiting Alex GO)

**Why** (beta research, `research-2026-07-05-beta-evidence.md`): the tracker,
ghost memory, and Insights funnel are only as good as their status data, and
users don't backfill statuses by hand. No mainstream tracker does local
mailbox-based status detection — market-wide gap = differentiator. This closes
the loop: rejections/interview invites land in email; the app should notice.

**Privacy identity (non-negotiable):** everything local. No cloud email API,
no telemetry, message bodies never persisted. This feature is the strongest
possible test of the "your data never leaves your machine" promise — design
for auditability.

## Shape

New `mailwatch/` package + a Settings card + a review dialog. Read-only IMAP
over SSL (stdlib `imaplib`, port 993, BODY.PEEK — never sets \Seen), polled
manually ("Scan now") and optionally after each daily run.

1. **Credentials**: host/port/username + app password. Password encrypted at
   rest with Windows DPAPI (`CryptProtectData` via ctypes — zero new deps,
   per-user key), stored in `USER_DATA_DIR/mailwatch.cred` (gitignored like
   network.json). UI masks to last-4. Presets: Gmail / Outlook.com / custom
   IMAP, each with an app-password how-to link (Gmail requires 2FA+app
   password; OAuth is explicitly out of beta scope — documented).
2. **Scan**: `SEARCH SINCE <last-cursor>` (cursor in tracker.db
   `mailwatch_state`), headers-first. A message is _relevant_ if sender domain
   ∈ ATS map (greenhouse.io, lever.co, ashbyhq.com, myworkday.com, icims.com,
   smartrecruiters.com, bamboohr.com…) OR sender/subject matches a tracked
   application's canonical company (reuse `coverage.entity.canonicalize_company`
   — same matcher the referral engine uses).
3. **Classify** (deterministic local rules first — BYO-AI philosophy): regex
   phrase banks → `rejected` ("unfortunately", "other candidates", "not moving
   forward"), `interview` ("schedule", "availability", "phone screen"),
   `assessment` (OA/HackerRank/Codility links), `ack` (auto-receipt). Ambiguous
   → optional BYO-AI clipboard prompt, same pattern as re-rank.
4. **Propose, never apply**: results land in a review dialog — "Detected 3
   updates: Kroger → Rejected (email Tue)…" with per-row accept/skip. Statuses
   change ONLY on user accept (the inclusion-over-precision analog: suggest,
   the USER decides). Accepted changes go through the normal tracker update
   path (applog audit line: `source=mailwatch`).
5. **Persistence**: `mailwatch_matches` table = message-id, date, matched
   application id, proposed status, 200-char snippet. Bodies never stored.

## Test plan

Fake-IMAP transcripts (no network) through scan→classify→propose; phrase-bank
corpus tests per class (incl. hard negatives: newsletters from ATS domains,
"interview tips" marketing); DPAPI round-trip; matcher tests vs canonical
company edge cases; a pin test that no code path writes a status without a
user-accept flag.

## Risks / open

- False positives → mitigated by review-before-apply + hard-negative corpus.
- Provider quirks (Gmail folder names, O365 throttling) → preset-specific
  mailbox lists ("INBOX" + Gmail "[Gmail]/All Mail" optional).
- **Needs Alex GO before building** (credential-holding feature; he should
  approve the DPAPI-file approach vs Windows Credential Manager first).
