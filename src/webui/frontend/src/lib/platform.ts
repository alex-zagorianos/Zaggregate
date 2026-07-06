/* Platform detection for keyboard-hint glyphs. On macOS the palette shortcut is
 * ⌘K; everywhere else (Windows/Linux — the vast majority of this app's users) it
 * is Ctrl+K. Showing a ⌘ on Windows (the Phase-0 bug) reads as wrong, so we only
 * render the command glyph on a real Mac. Guarded for SSR/tests (no navigator). */

export function isMac(): boolean {
  if (typeof navigator === "undefined") return false;
  // navigator.platform is deprecated but still the most reliable Mac signal in
  // browsers; fall back to userAgent. userAgentData.platform is the future path.
  const p =
    (navigator as { userAgentData?: { platform?: string } }).userAgentData
      ?.platform ||
    navigator.platform ||
    navigator.userAgent ||
    "";
  return /mac/i.test(p);
}

/** The mod-key label for the current platform: "⌘" on Mac, "Ctrl" elsewhere. */
export function modKeyLabel(): string {
  return isMac() ? "⌘" : "Ctrl";
}
