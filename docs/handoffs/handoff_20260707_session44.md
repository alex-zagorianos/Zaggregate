# Handoff — 2026-07-07, Session 44: Releases pipeline + Executables/ slim

**State: LIVE on the public repo.** Private origin at `9730351`, public
master fast-forwarded `b5fdb50..ea28750`. Suite 3,250 passed / 2 skipped.

## What Alex asked

"Fix what needs to be fixed/added for a releases pipeline, as well as what is
needed to slim the 50 MB per version."

## What shipped

### 1. GitHub Actions release pipeline (`.github/workflows/release.yml`)

Push a `v*` tag to the public repo and CI does everything: checks the tag
against `config.APP_VERSION` (hyphenated tags like `v1.2.3-beta1` publish as
pre-releases), runs the packaging tests, builds
`dist/Zaggregate-v{ver}.zip` + `SHA256SUMS.txt` with `src/build_package.py`,
re-verifies the checksum, and publishes the GitHub Release with both assets.
Guards: `if: github.repository == 'alex-zagorianos/Zaggregate'` so the
private Job-Program mirror (which carries the same file) never builds or
double-publishes; `--verify-tag`; `permissions: contents: write` only.

**Gotcha caught by a YAML parse-check before push:** a PowerShell here-string
inside a `run: |` block is a landmine — its closing `"@` must sit at column 0,
which terminates the YAML block scalar (`could not find expected ':'`). The
release notes are now built with an array `-join "`n"` (dry-run in PS 5.1
rendered the exact intended markdown).

### 2. Executables/ slimmed to a pointer (the 50 MB fix)

The S43c committed onedir is retired: `git rm` of ~1,300 files. Going forward
**zero app payload enters git history per release** — the zip is a Release
asset only.

- `refresh_executables()` (src/build_package.py) now just regenerates the
  version-stamped pointer README (→ releases/latest) and sweeps any stale
  payload from the retired S43b (nested zip) / S43c (onedir) layouts.
- `.gitignore`: the `!Executables/**` un-ignore block is replaced by an
  explicit payload block (`Executables/JobProgram/`, `Executables/*.zip`,
  `Executables/SHA256SUMS.txt`) so the onedir can never sneak back in.
- `.gitattributes`: the `Executables/** -text` byte-exact rule dropped (no
  tracked binary payload anymore).
- Root README ("Download for Windows" + packaged Quick start + repo layout)
  and docs/BUILD.md now route downloads to the Release assets; BUILD.md
  gained a "Publishing a release" section documenting the tag flow.
- Tests: the Executables README kit test re-pinned to `releases/latest` +
  the release zip name; a new test pins refresh's pointer+sweep behavior.

Still IN history: the one ~50 MB S43b/c payload already committed — that is
what `slim-history.ps1` removes (below, held).

### 3. Release ops rewired (`%USERPROFILE%\job-program-public-release\`)

- **`release.ps1` v2**: no local build/upload anymore. Verifies the rewrite
  mirror matches GitHub, reads `APP_VERSION` off the public master, tags
  `v<version>`, pushes the tag — Actions publishes the Release. The
  About/topics `gh repo edit` runs only if gh is authed (else prints the
  reminder; web UI works too).
- **Republish pushes are now HEADS-ONLY** (`"refs/heads/*:refs/heads/*"`),
  never `--mirror`: a fresh rewrite mirror has no tags, so a `--mirror` push
  would delete the release tags and their Releases. Recorded in the runbook +
  PUBLISH.md; today's two public pushes used the new form.
- **`slim-history.ps1` — STAGED, HELD for Alex's explicit go (force-push).**
  Re-runs the deterministic rewrite with 3 extra purge paths
  (Executables/JobProgram, the S43b zip, its SHA256SUMS) and force-pushes
  public master, dropping the committed payload from history. Safety gates:
  typed SLIM/PUSH confirmations, refuses if the public repo has any tags
  (they would strand on pre-rewrite commits and keep the blobs alive), pauses
  for the manual PII greps before pushing. **After it runs once, the 3 paths
  become part of the canonical republish recipe permanently** (runbook
  updated with this rule) — omitting them later would reintroduce the blobs
  and break fast-forward.

## Verification record

- Kit tests 14/14; full suite 3,250 passed / 2 skipped.
- Republish rewrite verified before each push: 20-pattern PII battery
  (fixed-string, case-insensitive, blobs + commit messages) all zero — with
  the harness first sanity-checked against a known-hit pattern (256,962
  hits on "import"); all 9 purge paths absent from every tree; authors =
  Alex only; fast-forward proven via `merge-base --is-ancestor`.
- Public HEAD tree spot-checked: `Executables/` = README.md only;
  `.github/workflows/release.yml` present.
- Workflow YAML parsed clean (8 steps); notes construction + prerelease
  branch dry-run in PowerShell.

## Alex's go-live (in order)

1. `powershell -File C:\Users\alex_\job-program-public-release\slim-history.ps1`
   — the force-push blob drop. Do this BEFORE the first tag (it refuses
   afterwards). Needs your explicit go by design.
2. `powershell -File C:\Users\alex_\job-program-public-release\release.ps1`
   — tags v1.0.0, Actions builds + publishes the Release; the in-app update
   check and the README/Executables links go live with it.
3. Optional: `gh auth login` once, re-run release.ps1 (or use the web UI) for
   the About blurb + topics.

## Open (unchanged)

Auto-update pipeline phase 2 (Velopack — 2 design calls still open), scoring
tune-up GOs, mecheng/eng2/proj-x ruling, wave-3 design GOs.
