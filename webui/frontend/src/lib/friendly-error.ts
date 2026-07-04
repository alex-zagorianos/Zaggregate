import { ApiError } from "@/api/client";

/* A single guard for the "raw error leaks to the user" failure mode: an
 * ApiError's message is server-authored and safe to show (it's already the
 * friendly envelope `error` string); anything else (a thrown non-ApiError, a
 * network TypeError, undefined) falls back to a calm, generic message rather
 * than a stack trace or "[object Object]". */

/** Turn a caught `unknown` into a string safe to show in a toast/inline error.
 * ApiError -> its message; anything else -> `fallback`. */
export function friendlyError(
  e: unknown,
  fallback = "Please try again.",
): string {
  if (e instanceof ApiError) return e.message || fallback;
  return fallback;
}

/** Guard a raw server-supplied error string (e.g. a run console's `snap.error`)
 * before showing it verbatim: trims it, and swaps in a calm message when it
 * looks like a leaked traceback (contains "Traceback" or spans multiple lines)
 * rather than a short human-readable failure reason. Null/undefined -> the
 * fallback; a normal one-line server message passes through unchanged. */
export function friendlyServerError(
  raw: string | null | undefined,
  fallback = "The run failed — see the console log for details.",
): string {
  const s = (raw ?? "").trim();
  if (!s) return fallback;
  if (s.includes("Traceback") || s.split("\n").length > 2) return fallback;
  return s;
}
