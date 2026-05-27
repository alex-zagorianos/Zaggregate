# Claude Code Session — Job Search App & Resume Tool
## Project Kickoff Prompt

---

## CONTEXT

I am building a job search tool and resume generation pipeline for personal use. This is a future-planning project — I am not actively job searching yet. The goal is to have a working local tool ready when I am.

My background: Mechanical Design Engineer with strong controls/software depth. Based in Cincinnati, OH. Open to relocation. Targeting roles in controls/embedded, mechanical/machine design, aerospace/defense, manufacturing automation, and R&D. Salary target ~$85–100K+.

---

## WHAT WE ARE BUILDING

### Phase 1 — Job Search Scraper (build first)
A local Python application that:
- Queries a job search API (prefer **JSearch via RapidAPI** or **Adzuna** — free tiers) for relevant roles
- Filters by: role keywords, location (Cincinnati + remote), and optionally salary
- Outputs results to a clean HTML file or simple local UI I can browse
- Saves results to CSV for later reference
- Target role keywords: controls engineer, embedded systems engineer, mechatronics, mechanical design engineer, machine design, manufacturing automation, R&D engineer, aerospace engineer

### Phase 2 — Resume/Cover Letter Generator (build second)
A simple tool or script that:
- Takes a job posting (pasted as text) + my `experience.md` master file as inputs
- Calls the Anthropic API to generate a tailored resume and cover letter
- Outputs clean, formatted documents (PDF or DOCX preferred)
- This avoids me needing to manually paste into Claude.ai every time

---

## TECH PREFERENCES
- **Language:** Python preferred
- **Target OS:** Windows (should run as a script or simple .exe eventually)
- **UI:** Minimal — CLI is fine for Phase 1, simple GUI or web UI acceptable for Phase 2
- **API keys needed:** JSearch (RapidAPI) or Adzuna for job scraping; Anthropic API key for Phase 2 (user has API access)

---

## MY EXPERIENCE FILE
I have a master `experience.md` file that contains my full career history, skills, job search criteria, and resume generation notes. It is the source of truth for all resume/cover letter generation. I will provide this file at the start of the session.

---

## SESSION GOALS (in order)
1. Set up project folder structure
2. Get Phase 1 job scraper working with at least one API source
3. Test with my target keywords and Cincinnati location
4. If time allows, scaffold Phase 2 Anthropic API integration

---

## NOTES
- Keep API calls minimal during dev/testing to preserve free tier limits
- Code should be clean and modular — Phase 1 and Phase 2 should be separable
- I may want to package this as an .exe eventually using PyInstaller — keep that in mind for dependencies
- Do not hardcode API keys — use a .env file or config file pattern from the start
