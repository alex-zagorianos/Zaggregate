"""'Connect job sources' dialog — free-signup URLs + credential entry.

Several high-reach job sources need a FREE key (Adzuna, USAJobs, Jooble,
Careerjet, CareerOneStop). This dialog lists each one with its signup URL, a
masked entry per credential, a Save button that writes to secrets/ (the same
mechanism the 'Connect your AI' box uses), and a per-source Test button that does
ONE tiny live probe so a user can confirm a pasted key works.

The other builder wires the Tools-menu entry; this module exposes open_dialog(parent).

Design constraints (repo rules): ASCII-only text (Tk 8.6 renders emoji
monochrome), headless-safe (a Toplevel is only built when a display exists), and
the live probe NEVER runs under pytest (PYTEST_CURRENT_TEST guard) and degrades
cleanly offline.
"""
import os
import webbrowser

import config
from ui import settings

# --- Source catalog: field metadata drives the whole dialog --------------------
# Each source: a title, the free-signup URL, and its credential fields. A field is
# (secret_name, label). secret_name indexes config.SOURCE_SECRET_FILES and
# settings.get/set_api_key.
SOURCES = [
    {
        "key": "adzuna",
        "title": "Adzuna (aggregator, ~19 countries)",
        "url": "https://developer.adzuna.com/",
        "fields": [
            ("adzuna_app_id", "App ID"),
            ("adzuna_app_key", "App Key"),
        ],
    },
    {
        "key": "usajobs",
        "title": "USAJobs (US federal jobs)",
        # The API-key REQUEST page (not the generic dev home) so the button lands
        # the user straight on the free-key form.
        "url": "https://developer.usajobs.gov/apirequest/",
        "fields": [
            ("usajobs_api_key", "API Key"),
            ("usajobs_email", "Registered Email"),
        ],
    },
    {
        "key": "jooble",
        "title": "Jooble (aggregator)",
        "url": "https://jooble.org/api/about",
        "fields": [
            ("jooble_api_key", "API Key"),
        ],
    },
    {
        "key": "careerjet",
        "title": "Careerjet (aggregator)",
        # The Publisher signup issues the affiliate ID the API needs — link there
        # directly rather than the generic partners landing page.
        "url": "https://www.careerjet.com/partners/publishers/",
        "fields": [
            ("careerjet_affid", "Affiliate ID"),
        ],
    },
    {
        "key": "careeronestop",
        "title": "CareerOneStop (US DOL / NLx, ~3.5M US jobs/day)",
        "url": "https://www.careeronestop.org/Developers/WebAPI/registration.aspx",
        "fields": [
            ("careeronestop_user_id", "User ID"),
            ("careeronestop_token", "API Token"),
        ],
    },
]


# --- Reference-only sources ----------------------------------------------------
# Two more free sources power features outside the credential-entry flow above:
# SerpApi backs the Inbox "reach" badge (and can act as a Google-Jobs backend) and
# JSearch aggregates the big walled boards (Indeed/LinkedIn/Glassdoor) via RapidAPI.
# Both are configured elsewhere (SERPAPI_KEY / secrets/serpapi_key, and
# JSEARCH_RAPIDAPI_KEY in .env), so here we surface their FREE-key signup links for
# completeness — a one-click "Get a free key" for every source the app can use.
REFERENCE_SOURCES = [
    ("SerpApi (reach badge / Google Jobs, free 250/mo)",
     "https://serpapi.com/users/sign_up"),
    ("JSearch via RapidAPI (Indeed / LinkedIn / Glassdoor, free 200/mo)",
     "https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch"),
]


def _in_pytest() -> bool:
    return bool(os.getenv("PYTEST_CURRENT_TEST"))


# --- paste helpers (§6.6) ------------------------------------------------------
# Adzuna's developer page hands the user an Application ID (an 8-hex-digit string)
# and an Application Key (a 32-hex-digit string) on ONE screen. A user copying
# "both" (or copying the page region) lands a blob with both values; splitting it
# client-side turns two error-prone copies into one paste. Pure + regex-only so
# it is unit-testable without a Tk root.
import re as _re

# App ID: exactly 8 hex chars; App Key: exactly 32 hex chars. Anchored on token
# boundaries so they don't match substrings of a longer run.
_ADZUNA_ID_RE = _re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{8}(?![0-9a-fA-F])")
_ADZUNA_KEY_RE = _re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])")


def split_adzuna_paste(text: str) -> tuple[str, str]:
    """Best-effort extraction of (app_id, app_key) from a pasted blob that may
    contain both Adzuna values (labeled or not). Returns ('', '') for either part
    it can't find. Never raises.

    Recognizes the two by SHAPE (8-hex id, 32-hex key) so it works whether the
    user pasted 'Application ID: xxxx  Application Key: yyyy', two lines, or the
    two tokens space-separated. If only one shape is present, only that slot is
    filled."""
    s = text or ""
    key_m = _ADZUNA_KEY_RE.search(s)
    app_key = key_m.group(0) if key_m else ""
    # Find an 8-hex id that is NOT the first 8 chars of the 32-hex key we matched.
    app_id = ""
    for m in _ADZUNA_ID_RE.finditer(s):
        if key_m and key_m.start() <= m.start() < key_m.end():
            continue  # inside the key token
        app_id = m.group(0)
        break
    return app_id, app_key


def looks_like_adzuna_paste(text: str) -> bool:
    """True when a pasted blob plausibly contains Adzuna credentials (a 32-hex key,
    or an 8-hex id) — used to decide whether to offer the split. Cheap/pure."""
    app_id, app_key = split_adzuna_paste(text)
    return bool(app_id or app_key)


def test_source(source_key: str) -> tuple[bool, str]:
    """Do ONE tiny live probe for a source and report (ok, message). Guarded:
    returns a benign 'skipped' result under pytest or when the source's key is
    unset, and turns any network/offline error into a clean (False, message)
    rather than raising. This is the button's worker; separated out so it is
    unit-testable without a Tk root."""
    if _in_pytest():
        return (False, "skipped (test mode)")

    if source_key == "adzuna":
        if not (settings.get_api_key("adzuna_app_id")
                and settings.get_api_key("adzuna_app_key")):
            return (False, "App ID and App Key required")
        try:
            from search.adzuna_client import AdzunaClient
            c = AdzunaClient(cache_enabled=False)
            raw = c.search("engineer", location="", page=1)
            n = len(c.parse_results(raw, "engineer"))
            return (True, f"OK - {n} sample result(s)")
        except Exception as e:
            return (False, f"{type(e).__name__}: {e}")

    if source_key == "usajobs":
        if not (settings.get_api_key("usajobs_api_key")
                and settings.get_api_key("usajobs_email")):
            return (False, "API Key and Email required")
        try:
            from search.usajobs_client import USAJobsClient
            c = USAJobsClient(cache_enabled=False)
            raw = c.search("engineer", location="", page=1)
            n = len(c.parse_results(raw, "engineer"))
            return (True, f"OK - {n} sample result(s)")
        except Exception as e:
            return (False, f"{type(e).__name__}: {e}")

    if source_key == "jooble":
        if not settings.get_api_key("jooble_api_key"):
            return (False, "API Key required")
        try:
            from search.jooble_client import JoobleClient
            c = JoobleClient(cache_enabled=False)
            raw = c.search("engineer", location="")
            n = len(c.parse_results(raw, "engineer"))
            return (True, f"OK - {n} sample result(s)")
        except Exception as e:
            return (False, f"{type(e).__name__}: {e}")

    if source_key == "careerjet":
        if not settings.get_api_key("careerjet_affid"):
            return (False, "Affiliate ID required")
        try:
            from search.careerjet_client import CareerjetClient
            c = CareerjetClient(cache_enabled=False)
            raw = c.search("engineer", location="")
            n = len(c.parse_results(raw, "engineer"))
            return (True, f"OK - {n} sample result(s)")
        except Exception as e:
            return (False, f"{type(e).__name__}: {e}")

    if source_key == "careeronestop":
        if not (settings.get_api_key("careeronestop_user_id")
                and settings.get_api_key("careeronestop_token")):
            return (False, "User ID and API Token required")
        try:
            from search.careeronestop_client import CareerOneStopClient
            c = CareerOneStopClient(cache_enabled=False)
            raw = c.search("nurse", location="", page=1)
            n = len(c.parse_results(raw, "nurse"))
            return (True, f"OK - {n} sample result(s)")
        except Exception as e:
            return (False, f"{type(e).__name__}: {e}")

    return (False, "unknown source")


def open_dialog(parent=None):
    """Build and show the 'Connect job sources' Toplevel. Returns the Toplevel,
    or None if there is no display (headless). The other builder calls this from
    the Tools menu."""
    import tkinter as tk
    from tkinter import messagebox, ttk

    try:
        win = tk.Toplevel(parent) if parent is not None else tk.Tk()
    except tk.TclError:
        return None  # no display -> caller (and tests) treat as a no-op

    win.title("Connect job sources")
    win.geometry("560x560")

    header = ttk.Label(
        win,
        text=("Add a FREE key to unlock more job sources. Each key stays on this "
              "computer (in your data folder) and is never uploaded."),
        wraplength=520, justify="left",
    )
    header.pack(fill="x", padx=12, pady=(12, 6))

    # Scrollable body so all sources fit on small screens.
    canvas = tk.Canvas(win, highlightthickness=0)
    scroll = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
    body = ttk.Frame(canvas)
    body.bind("<Configure>",
              lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=body, anchor="nw")
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=6)
    scroll.pack(side="right", fill="y", padx=(0, 6), pady=6)

    entries: dict = {}   # secret_name -> StringVar

    for src in SOURCES:
        box = ttk.LabelFrame(body, text=src["title"])
        box.pack(fill="x", expand=True, padx=6, pady=6)

        # Deep-link: a real button (not just link text) straight to the FREE
        # registration page, so the user lands on the exact form (§6.6 / Pattern
        # 1a). Adzuna + CareerOneStop are the two headline keys, but every source
        # gets its own button for consistency.
        reg_row = ttk.Frame(box)
        reg_row.grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 2))
        ttk.Button(reg_row, text="Get a free key \N{RIGHTWARDS ARROW}",
                   command=lambda u=src["url"]: webbrowser.open(u)).pack(side="left")
        link = ttk.Label(reg_row, text="  " + src["url"],
                         foreground="#0d5eaf", cursor="hand2")
        link.pack(side="left")
        link.bind("<Button-1>", lambda e, u=src["url"]: webbrowser.open(u))

        for i, (secret_name, label) in enumerate(src["fields"], start=1):
            ttk.Label(box, text=label + ":").grid(
                row=i, column=0, sticky="e", padx=(8, 4), pady=2)
            var = tk.StringVar(value=settings.get_api_key(secret_name))
            entries[secret_name] = var
            ttk.Entry(box, textvariable=var, width=40, show="*").grid(
                row=i, column=1, sticky="w", padx=4, pady=2)

        status = ttk.Label(box, text="", wraplength=320, justify="left")
        status.grid(row=99, column=0, columnspan=3, sticky="w", padx=8, pady=(2, 6))

        # Green/red inline feedback colors (§6.6 / Clerk instant-validity pattern).
        _OK_FG, _BAD_FG, _NEUTRAL_FG = "#1a7f37", "#b3261e", ""

        def _save(s=src, st=status):
            ok = True
            for secret_name, _ in s["fields"]:
                if not settings.set_api_key(secret_name, entries[secret_name].get()):
                    ok = False
            st.config(
                text="Saved." if ok else "Could not save (check folder permissions).",
                foreground=(_OK_FG if ok else _BAD_FG))

        def _run_test(s=src, st=status):
            """Save the current field values, run the ONE live probe, and show a
            green OK / red failure inline. Shared by the Test button and the
            auto-test-on-paste path."""
            for secret_name, _ in s["fields"]:
                settings.set_api_key(secret_name, entries[secret_name].get())
            st.config(text="Testing...", foreground=_NEUTRAL_FG)
            st.update_idletasks()
            ok, msg = test_source(s["key"])
            st.config(text=("OK - " + msg if ok else "Check your key - " + msg),
                      foreground=(_OK_FG if ok else _BAD_FG))

        # Auto-run the live test shortly after a paste/edit settles, so the user
        # sees green/red without hunting for a button (§6.6). Debounced per source
        # so rapid keystrokes fire only one probe; guarded so it never raises into
        # the Tk callback. Under pytest test_source() self-skips, so this is inert.
        _pending = {"job": None}

        def _schedule_autotest(s=src, st=status, pend=_pending):
            job = pend["job"]
            if job is not None:
                try:
                    box.after_cancel(job)
                except Exception:
                    pass
            # Only probe once every required field has some content.
            if all(entries[n].get().strip() for n, _ in s["fields"]):
                pend["job"] = box.after(600, lambda: _run_test(s, st))

        for secret_name, _ in src["fields"]:
            entries[secret_name].trace_add(
                "write", lambda *_a, s=src, st=status: _schedule_autotest(s, st))

        btns = ttk.Frame(box)
        btns.grid(row=100, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 6))
        ttk.Button(btns, text="Save", command=_save).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Test", command=_run_test).pack(side="left")

        # Adzuna hands out App ID + App Key on one page: a single "Paste both"
        # splits a clipboard blob into the two fields (§6.6 / Pattern 1c).
        if src["key"] == "adzuna":
            def _paste_both(st=status):
                try:
                    blob = win.clipboard_get()
                except Exception:
                    st.config(text="Clipboard is empty.", foreground=_BAD_FG)
                    return
                app_id, app_key = split_adzuna_paste(blob)
                if not (app_id or app_key):
                    st.config(
                        text="Couldn't find Adzuna values in the clipboard - "
                             "paste the App ID / App Key manually.",
                        foreground=_BAD_FG)
                    return
                if app_id:
                    entries["adzuna_app_id"].set(app_id)
                if app_key:
                    entries["adzuna_app_key"].set(app_key)
                # The trace on the entries auto-schedules a test when both are set.
                st.config(text="Pasted from clipboard.", foreground=_OK_FG)
            ttk.Button(btns, text="Paste both from clipboard",
                       command=_paste_both).pack(side="left", padx=(6, 0))

    # More free sources — link-only (configured elsewhere), so every source the
    # app can use has a one-click "Get a free key" here.
    ref = ttk.LabelFrame(body, text="More free sources")
    ref.pack(fill="x", expand=True, padx=6, pady=6)
    ttk.Label(ref, text=("These power extra features and are set up elsewhere "
                         "(.env / secrets), but each has a free key:"),
              wraplength=460, justify="left").grid(
        row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(6, 2))
    for i, (label, url) in enumerate(REFERENCE_SOURCES, start=1):
        rrow = ttk.Frame(ref)
        rrow.grid(row=i, column=0, columnspan=2, sticky="w", padx=8, pady=2)
        ttk.Button(rrow, text="Get a free key \N{RIGHTWARDS ARROW}",
                   command=lambda u=url: webbrowser.open(u)).pack(side="left")
        rlink = ttk.Label(rrow, text="  " + label, foreground="#0d5eaf",
                          cursor="hand2")
        rlink.pack(side="left")
        rlink.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

    def _save_all_and_close():
        saved = 0
        for src in SOURCES:
            for secret_name, _ in src["fields"]:
                if settings.set_api_key(secret_name, entries[secret_name].get()):
                    saved += 1
        win.destroy()

    footer = ttk.Frame(win)
    footer.pack(fill="x", padx=12, pady=(0, 12))
    ttk.Button(footer, text="Save all & close",
               command=_save_all_and_close).pack(side="right")
    ttk.Button(footer, text="Close", command=win.destroy).pack(side="right", padx=6)

    return win
