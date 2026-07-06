/* Clipboard copy with a graceful fallback — the "Copy prompt" chokepoint for the
 * BYO-AI flows (Apply Queue resume/batch/fit prompts, Resume tab prompt).
 *
 * navigator.clipboard.writeText is the modern path but needs a secure context +
 * permission; on 127.0.0.1 it IS a secure context, but a denied permission or an
 * old surface can still reject. We fall back to a hidden-textarea + execCommand so
 * the copy still lands. Returns true on success; the caller toasts accordingly and
 * (on false) can surface the text for a manual copy. Never throws. */
export async function copyText(text: string): Promise<boolean> {
  if (
    typeof navigator !== "undefined" &&
    navigator.clipboard &&
    typeof navigator.clipboard.writeText === "function"
  ) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // fall through to the legacy path
    }
  }
  return legacyCopy(text);
}

function legacyCopy(text: string): boolean {
  if (typeof document === "undefined") return false;
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    // Keep it off-screen + non-scrolling so nothing flashes.
    ta.style.position = "fixed";
    ta.style.top = "-9999px";
    ta.style.left = "-9999px";
    ta.setAttribute("readonly", "");
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  } catch {
    return false;
  }
}
