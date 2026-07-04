import * as React from "react";
import { endpoints, type ThemeMode } from "@/api/client";

/* Theme is server-authoritative (ui_settings.json via /api/settings/theme) so it
 * matches the tk app and survives reloads. Flow:
 *   • boot: index.html's inline script applied the localStorage cache pre-paint
 *     (no flash); this provider then fetches the server value and reconciles.
 *   • toggle: optimistic <html data-theme> flip + localStorage write, then PUT.
 *     A failed PUT is non-fatal (local view still flips); logged, not thrown.
 */

const STORAGE_KEY = "zg-theme";

function applyDom(mode: ThemeMode) {
  const el = document.documentElement;
  if (mode === "dark") el.setAttribute("data-theme", "dark");
  else el.removeAttribute("data-theme");
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* private-mode / storage-disabled: DOM state still applied */
  }
}

function cachedMode(): ThemeMode {
  try {
    return localStorage.getItem(STORAGE_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

interface ThemeContextValue {
  mode: ThemeMode;
  toggle: () => void;
  setMode: (mode: ThemeMode) => void;
}

const ThemeContext = React.createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = React.useState<ThemeMode>(cachedMode);

  // Reconcile with the server value once on mount.
  React.useEffect(() => {
    let alive = true;
    endpoints
      .getTheme()
      .then((r) => {
        if (alive && (r.mode === "light" || r.mode === "dark")) {
          setModeState(r.mode);
          applyDom(r.mode);
        }
      })
      .catch(() => {
        /* offline / API down: keep the cached mode already applied at boot */
      });
    return () => {
      alive = false;
    };
  }, []);

  const setMode = React.useCallback((next: ThemeMode) => {
    setModeState(next);
    applyDom(next);
    endpoints.setTheme(next).catch((e) => {
      console.warn("theme persist failed", e);
    });
  }, []);

  const toggle = React.useCallback(() => {
    setMode(mode === "dark" ? "light" : "dark");
  }, [mode, setMode]);

  const value = React.useMemo(
    () => ({ mode, toggle, setMode }),
    [mode, toggle, setMode],
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = React.useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within <ThemeProvider>");
  return ctx;
}
