import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { useOnboarding, queryKeys } from "@/api/queries";
import { SetupWizard } from "./SetupWizard";

/* The app-level onboarding gate. Wraps the whole app: it reads GET /api/onboarding
 * once; if the user isn't onboarded (and hasn't skipped this session), it renders
 * the full-screen SetupWizard takeover OVER the app. Onboarded users (or those who
 * skip) get the normal app immediately.
 *
 * - Not onboarded + not skipped  → wizard takeover (children still mounted behind,
 *   but visually covered — so finishing reveals a warm inbox with no reload flash).
 * - Skip                         → hide the wizard for this session (no server
 *   write); it reappears next launch, matching the tk "explore first" affordance.
 * - Finish / AI apply            → the apply mutation invalidated everything incl.
 *   the onboarding flag; we also route to the Inbox so the user lands there.
 *
 * While the state loads we render children (the app shell) rather than a spinner —
 * onboarding is the exception, not the rule, so returning users see no flash. If a
 * brand-new user's very first frame shows the app for a beat before the wizard
 * mounts, that's acceptable and rare; the query is fast + cached. */

export function OnboardingGate({ children }: { children: React.ReactNode }) {
  const { data, isLoading } = useOnboarding();
  const [skipped, setSkipped] = React.useState(false);
  const navigate = useNavigate();
  const qc = useQueryClient();

  // Show the wizard only once we KNOW the user isn't onboarded (never during the
  // initial load — that would flash the takeover at returning users).
  const needsOnboarding = !isLoading && data?.onboarded === false && !skipped;

  const onComplete = React.useCallback(() => {
    // The apply mutation already invalidated the onboarding flag; make sure the
    // gate re-reads it (now onboarded:true) and land on the Inbox.
    qc.invalidateQueries({ queryKey: queryKeys.onboarding });
    navigate("/inbox");
  }, [navigate, qc]);

  const onSkip = React.useCallback(() => setSkipped(true), []);

  return (
    <>
      {children}
      {needsOnboarding && data && (
        <SetupWizard
          prefill={data.prefill}
          onComplete={onComplete}
          onSkip={onSkip}
        />
      )}
    </>
  );
}
