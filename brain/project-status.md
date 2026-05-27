# Project Status

#status #roadmap

## Phase 1 — Job Scraper ✅ COMPLETE (2026-05-26)

- [x] Adzuna API client with rate limiting and caching
- [x] Multi-keyword search engine with deduplication
- [x] HTML report: filterable by source, keyword, searchable, sortable
- [x] CSV export
- [x] CLI: `py -m search.cli` with full flags
- [x] Multi-source architecture (base class + JSearch + USAJobs clients)
- [ ] JSearch key not yet added to .env
- [ ] USAJobs key not yet added to .env
- [ ] First git commit not yet made

## Phase 2 — Resume/Cover Letter Generator ⏳ NOT STARTED

- [ ] `resume/experience_parser.py` — parse experience.md into structured sections
- [ ] `resume/generator.py` — Claude API prompt construction (Sonnet 4)
- [ ] `resume/docx_builder.py` — python-docx formatting
- [ ] `resume/app.py` + `resume/templates/index.html` — Flask local web UI
- [ ] Anthropic API key not yet added to .env

## Outstanding Info Needed from Alex

- [ ] ERP tech stack (for experience.md)
- [ ] More G90 experience detail
- [ ] GD&T tools used (software + standard)

## Git Status

- Repo initialized, remote set to `git@github.com:alex-zagorianos/Job-Program.git`
- SSH key configured
- **No commits yet** — initial commit still pending
- Pre-push security check required before every push (standing rule)
