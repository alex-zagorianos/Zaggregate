"""'Seed my area…' Tools-menu dialog — the GUI front door to Seed-My-Area Leg B.

Discovers local employers from the CareerOneStop Business Finder directory (the
same free key as the job feed), verifies each has a live ATS board, and adds the
verified ones to the registry, tagged for the user's field + metro. Zero AI.

Key-gated + honest: with NO CareerOneStop key the dialog shows a plain-English
message and a button that opens the existing 'Connect job sources' keys dialog,
rather than a dead form. The seed runs in a background thread (no GUI freeze, no
mainloop here); the field + metro prefill from the active project's config.

Kept deliberately small and self-contained so it does not collide with the other
builders' work on the wizard / AddCompaniesDialog / InboxTab / Kanban tab.
"""
from __future__ import annotations

import threading


def _active_field_and_metro() -> tuple[str, str]:
    """Prefill values from the active project's config; ('', '') if unavailable."""
    try:
        import workspace
        cfg = workspace.load_config() or {}
        return (str(cfg.get("industry") or "").strip(),
                str(cfg.get("location") or "").strip())
    except Exception:
        return ("", "")


def _has_careeronestop_key() -> bool:
    try:
        import config
        return bool(config.resolve_secret("CAREERONESTOP_USER_ID", "careeronestop_user_id")
                    and config.resolve_secret("CAREERONESTOP_TOKEN", "careeronestop_token"))
    except Exception:
        return False


def open_dialog(parent=None):
    """Build and show the 'Seed my area' Toplevel. Returns the Toplevel, or None
    when there is no display (headless / tests) — a clean no-op, never a raise."""
    import tkinter as tk
    from tkinter import ttk

    try:
        win = tk.Toplevel(parent) if parent is not None else tk.Tk()
    except tk.TclError:
        return None

    win.title("Seed my area")
    win.geometry("560x480")

    ttk.Label(
        win,
        text=("Find local employers for your field and add the ones with a live "
              "careers board to your company list — automatically, no AI needed. "
              "Uses the free CareerOneStop employer directory (US DOL)."),
        wraplength=520, justify="left",
    ).pack(fill="x", padx=12, pady=(12, 8))

    if not _has_careeronestop_key():
        _render_unkeyed(win, parent)
        return win

    _render_keyed(win, parent)
    return win


def _render_unkeyed(win, parent):
    """Honest 'no key' state: explain + a one-click route to the keys dialog."""
    from tkinter import ttk

    box = ttk.LabelFrame(win, text="A free key is needed first")
    box.pack(fill="x", padx=12, pady=8)
    ttk.Label(
        box,
        text=("Seed my area uses the CareerOneStop employer directory, which needs "
              "a free CareerOneStop key (a User ID + API Token). It's the same key "
              "that unlocks the CareerOneStop job feed, so you only register once.\n\n"
              "Click below to add it, then reopen this window."),
        wraplength=500, justify="left",
    ).pack(fill="x", padx=8, pady=8)

    def _open_keys():
        try:
            from ui import source_keys
            source_keys.open_dialog(parent or win)
        except Exception:
            import webbrowser
            webbrowser.open(
                "https://www.careeronestop.org/Developers/WebAPI/registration.aspx")

    btns = ttk.Frame(win)
    btns.pack(fill="x", padx=12, pady=(0, 12))
    ttk.Button(btns, text="Connect job sources (add key)…",
               command=_open_keys).pack(side="left")
    ttk.Button(btns, text="Close", command=win.destroy).pack(side="right")


def _render_keyed(win, parent):
    """The active form: field + metro inputs, a live-log run, verified-only save."""
    import tkinter as tk
    from tkinter import ttk

    field0, metro0 = _active_field_and_metro()
    form = ttk.Frame(win)
    form.pack(fill="x", padx=12, pady=4)
    ttk.Label(form, text="Field / industry:").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=3)
    field_var = tk.StringVar(value=field0)
    ttk.Entry(form, textvariable=field_var, width=36).grid(row=0, column=1, sticky="w", pady=3)
    ttk.Label(form, text="Area (City, ST / ZIP):").grid(row=1, column=0, sticky="e", padx=(0, 6), pady=3)
    metro_var = tk.StringVar(value=metro0)
    ttk.Entry(form, textvariable=metro_var, width=36).grid(row=1, column=1, sticky="w", pady=3)

    log_box = tk.Text(win, height=12, wrap="word", state="disabled")
    log_box.pack(fill="both", expand=True, padx=12, pady=(8, 4))

    def _append(line: str):
        # Marshal back onto the Tk thread; the worker calls this from a bg thread.
        def _do():
            log_box.config(state="normal")
            log_box.insert("end", line.rstrip() + "\n")
            log_box.see("end")
            log_box.config(state="disabled")
        try:
            win.after(0, _do)
        except Exception:
            pass

    state = {"running": False}

    def _run():
        if state["running"]:
            return
        industry = field_var.get().strip()
        metro = metro_var.get().strip()
        if not industry and not metro:
            _append("[seed] Enter a field and/or an area to search.")
            return
        state["running"] = True
        run_btn.config(state="disabled")
        _append(f"[seed] Seeding employers for {industry or '(any field)'} "
                f"near {metro or '(no area)'}…")

        def _work():
            try:
                from discover.seed_metro import seed_my_metro
                res = seed_my_metro(industry=industry, metro=metro, log=_append)
                if res.added:
                    _append(f"[seed] Done — added {res.added} verified local "
                            f"employer(s) to your list.")
                elif res.verified:
                    _append(f"[seed] Found {res.verified} live board(s) "
                            f"(already in your list).")
                elif res.note:
                    _append(f"[seed] {res.note}")
                else:
                    _append("[seed] No new verified employers this run.")
            except Exception as e:
                _append(f"[seed] Stopped: {type(e).__name__}: {e}")
            finally:
                state["running"] = False
                try:
                    win.after(0, lambda: run_btn.config(state="normal"))
                except Exception:
                    pass

        threading.Thread(target=_work, daemon=True).start()

    btns = ttk.Frame(win)
    btns.pack(fill="x", padx=12, pady=(0, 12))
    run_btn = ttk.Button(btns, text="Seed my area now", command=_run)
    run_btn.pack(side="left")
    ttk.Button(btns, text="Close", command=win.destroy).pack(side="right")
