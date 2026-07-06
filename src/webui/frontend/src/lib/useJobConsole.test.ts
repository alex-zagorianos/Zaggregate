import { describe, it, expect } from "vitest";

import { reconcileAction } from "./useJobConsole";

/* The pure branching behind useJobConsole's SSE error-reconcile (S40 live-test
 * fix 2). The browser's `error` event is ambiguous (terminal error frame vs
 * transport drop), so the hook closes the stream and fetches the job status;
 * reconcileAction maps that status to the one correct next step. The load-
 * bearing case is "running" → resubscribe: es.close() disables the browser's
 * native auto-reconnect, so a mid-run drop that ISN'T manually resubscribed
 * detaches the console forever — the finish never reaches onDone and the Inbox
 * never refetches (the live bug: handoff-attached first run completed with 46
 * rows, table stayed at 0). The hook wiring itself isn't render-testable here
 * (node env, no RTL); this pins the decision it delegates to. */

describe("reconcileAction", () => {
  it("failed → surface the failure", () => {
    expect(reconcileAction("failed")).toEqual({ kind: "failed" });
  });

  it("done → terminal handler with 'done' (origin reconcile at the call site)", () => {
    expect(reconcileAction("done")).toEqual({
      kind: "terminal",
      status: "done",
    });
  });

  it("cancelled → terminal handler with 'cancelled'", () => {
    expect(reconcileAction("cancelled")).toEqual({
      kind: "terminal",
      status: "cancelled",
    });
  });

  it("running → RESUBSCRIBE (the mid-run drop must not detach the console)", () => {
    expect(reconcileAction("running")).toEqual({ kind: "resubscribe" });
  });

  it("an unknown status is treated as still-running (keep listening, never silently detach)", () => {
    expect(reconcileAction("")).toEqual({ kind: "resubscribe" });
    expect(reconcileAction("queued")).toEqual({ kind: "resubscribe" });
  });
});
