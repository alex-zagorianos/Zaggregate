import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import {
  INBOX_RUN_HANDOFF_KEY,
  stashInboxRunJob,
  takeInboxRunJob,
} from "./inbox-run-handoff";

/* The Inbox run-console handoff (S40): the wizard stashes a started first-run job
 * id, the Inbox consumes-and-clears it (from a location.key-keyed effect — mount
 * alone misses the already-mounted-under-the-takeover case, see the module GOTCHA)
 * to attach its run console. Pure logic over sessionStorage — the vitest env is
 * node, so we install a minimal in-memory sessionStorage stub. */

function installSessionStorage(): Map<string, string> {
  const store = new Map<string, string>();
  const stub = {
    getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
    setItem: (k: string, v: string) => void store.set(k, String(v)),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
    key: (i: number) => Array.from(store.keys())[i] ?? null,
    get length() {
      return store.size;
    },
  };
  vi.stubGlobal("sessionStorage", stub);
  return store;
}

describe("inbox-run-handoff", () => {
  let store: Map<string, string>;
  beforeEach(() => {
    store = installSessionStorage();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("stashes a job id under the shared key and takes it back", () => {
    stashInboxRunJob("deadbeef");
    expect(store.get(INBOX_RUN_HANDOFF_KEY)).toBe("deadbeef");
    expect(takeInboxRunJob()).toBe("deadbeef");
  });

  it("CLEARS on take so a refresh doesn't resurrect the console", () => {
    stashInboxRunJob("abc123");
    expect(takeInboxRunJob()).toBe("abc123");
    // Gone after the first take.
    expect(store.has(INBOX_RUN_HANDOFF_KEY)).toBe(false);
    expect(takeInboxRunJob()).toBeNull();
  });

  it("returns null when nothing was stashed", () => {
    expect(takeInboxRunJob()).toBeNull();
  });

  it("already-mounted Inbox: a location.key re-fire consumes exactly once (S40 live-test fix)", () => {
    // Simulates the take() calls of the Inbox's location.key-keyed effect when
    // the tab was ALREADY mounted under the onboarding takeover:
    // 1st fire — initial mount, before the wizard stashes anything: a no-op.
    expect(takeInboxRunJob()).toBeNull();
    // The wizard stashes the started job id, then navigate("/inbox") mints a new
    // location.key on the SAME path — no remount, just an effect re-fire. That
    // re-fire must find and consume the stash…
    stashInboxRunJob("6f647bdc");
    expect(takeInboxRunJob()).toBe("6f647bdc");
    // …exactly once: the key is cleared, so any later navigations/re-fires are
    // no-ops (no stale console re-attach).
    expect(store.has(INBOX_RUN_HANDOFF_KEY)).toBe(false);
    expect(takeInboxRunJob()).toBeNull();
    expect(takeInboxRunJob()).toBeNull();
  });

  it("ignores a blank job id (no autorun / job couldn't start)", () => {
    stashInboxRunJob("");
    expect(store.has(INBOX_RUN_HANDOFF_KEY)).toBe(false);
    expect(takeInboxRunJob()).toBeNull();
  });

  it("survives sessionStorage throwing (best-effort, never crashes)", () => {
    vi.stubGlobal("sessionStorage", {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    });
    expect(() => stashInboxRunJob("x")).not.toThrow();
    expect(takeInboxRunJob()).toBeNull();
  });
});
