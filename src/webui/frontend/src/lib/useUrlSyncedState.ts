import * as React from "react";
import { useSearchParams } from "react-router-dom";

/* Generic URL <-> state sync, built for the Inbox filter bar (KNOWN_ISSUES: "Filter
 * state not URL-synced — back/refresh resets the Inbox view") but deliberately
 * codec-agnostic so any tab with view-filter state can reuse it.
 *
 * Contract:
 *  - `serialize(state) -> URLSearchParams` should OMIT default-valued fields (the
 *    codec owns "what counts as default", same as inbox-filter-state's `toParams`).
 *  - `deserialize(params) -> state` must be FAIL-OPEN: garbage/unknown values fall
 *    back to that field's default silently. Never throw, never let a bad URL
 *    filter everything out or crash the tab.
 *  - The hook writes with `replaceState` semantics (React Router's `{ replace:
 *    true }`) on every state change — never `pushState` — so typing in a search
 *    box doesn't spam browser history. Callers that already debounce their own
 *    rapid-fire field (e.g. the filter bar's local search-text state) can pass
 *    `debounceMs: 0`; the hook still offers its own debounce for callers that feed
 *    it undebounced updates directly. */

export interface UrlSyncedStateOptions<T> {
  /** Current state value (owned by the caller — this hook does not hold state). */
  state: T;
  /** State setter, called once on mount if the URL carries params (URL wins). */
  setState: (next: T) => void;
  /** State -> URL params. Must omit default fields for clean URLs. */
  serialize: (state: T) => URLSearchParams;
  /** URL params -> state. Must be fail-open (never throw; bad values -> defaults). */
  deserialize: (params: URLSearchParams) => T;
  /** Debounce (ms) before writing `state` changes to the URL. Default 300. */
  debounceMs?: number;
}

/** Keeps `state` mirrored into the URL query string (debounced replaceState) and,
 * on first mount, initializes from whatever the URL already carries. */
export function useUrlSyncedState<T>({
  state,
  setState,
  serialize,
  deserialize,
  debounceMs = 300,
}: UrlSyncedStateOptions<T>): void {
  const [searchParams, setSearchParams] = useSearchParams();

  // Read the setters/codec from refs so effects below don't need them in deps
  // (they're expected to be stable-ish, but re-running the mount-init effect on a
  // caller re-render would be wrong regardless).
  const setStateRef = React.useRef(setState);
  setStateRef.current = setState;
  const deserializeRef = React.useRef(deserialize);
  deserializeRef.current = deserialize;
  const serializeRef = React.useRef(serialize);
  serializeRef.current = serialize;

  // ── mount: URL wins over the caller's default state ────────────────────────
  const didInit = React.useRef(false);
  React.useEffect(() => {
    if (didInit.current) return;
    didInit.current = true;
    if (Array.from(searchParams.keys()).length === 0) return; // nothing to apply
    setStateRef.current(deserializeRef.current(searchParams));
    // Intentionally run once — this is a mount-time initializer, not a live sync
    // (live URL edits, e.g. back/forward, are handled by the popstate effect below).
  }, []);

  // ── back/forward: re-apply state when the URL changes out from under us ────
  // searchParams already reflects popstate navigation via React Router; re-derive
  // state whenever it changes so browser back/forward reloads the same view. Guard
  // against re-deriving right after OUR OWN write (see the write effect) by
  // comparing against the last string we wrote.
  const lastWrittenRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!didInit.current) return; // mount effect handles the first application
    const current = searchParams.toString();
    if (current === lastWrittenRef.current) return; // our own write; state already matches
    setStateRef.current(deserializeRef.current(searchParams));
    // Deps intentionally just [searchParams] — setStateRef/deserializeRef are
    // refs read via .current precisely so this effect doesn't need to depend
    // on the (possibly-unstable) setState/deserialize the caller passed in.
  }, [searchParams]);

  // ── state -> URL, debounced, replaceState (no history spam) ────────────────
  React.useEffect(() => {
    const t = setTimeout(() => {
      const next = serializeRef.current(state);
      const nextStr = next.toString();
      if (nextStr === searchParams.toString()) return;
      lastWrittenRef.current = nextStr;
      setSearchParams(next, { replace: true });
    }, debounceMs);
    return () => clearTimeout(t);
    // setSearchParams/searchParams intentionally excluded (see above) — this
    // effect only reacts to state/debounceMs changes.
  }, [state, debounceMs]);
}
