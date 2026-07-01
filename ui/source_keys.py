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
        "url": "https://developer.usajobs.gov/",
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
        "url": "https://www.careerjet.com/partners/",
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


def _in_pytest() -> bool:
    return bool(os.getenv("PYTEST_CURRENT_TEST"))


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

        link = ttk.Label(box, text="Get a free key: " + src["url"],
                         foreground="#0d5eaf", cursor="hand2")
        link.grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 2))
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

        def _save(s=src, st=status):
            ok = True
            for secret_name, _ in s["fields"]:
                if not settings.set_api_key(secret_name, entries[secret_name].get()):
                    ok = False
            st.config(
                text="Saved." if ok else "Could not save (check folder permissions).")

        def _test(s=src, st=status):
            for secret_name, _ in s["fields"]:
                settings.set_api_key(secret_name, entries[secret_name].get())
            st.config(text="Testing...")
            st.update_idletasks()
            ok, msg = test_source(s["key"])
            st.config(text=("Test: " + msg))

        btns = ttk.Frame(box)
        btns.grid(row=100, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 6))
        ttk.Button(btns, text="Save", command=_save).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Test", command=_test).pack(side="left")

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
