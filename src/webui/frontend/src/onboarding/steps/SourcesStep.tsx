import { PlugZap } from "lucide-react";

import { SourceCardGrid } from "@/tabs/sources/SourcesTab";
import { StepHead } from "./StepHead";

/* Step 6 — Connect sources. Embeds the exact SourcesTab card grid (reused, not
 * duplicated) so the user can add free keys mid-onboarding. Entirely optional —
 * the app works with the always-on sources; a key just widens the net. Always
 * valid to advance. */

export function SourcesStep() {
  return (
    <div className="max-w-3xl">
      <StepHead
        icon={<PlugZap className="size-4" />}
        eyebrow="Widen the net"
        title="Connect job sources"
        sub="Optional free keys pull in more boards. Each stays on this computer — never uploaded. You can always add these later from the gear menu."
      />
      <div className="mt-8">
        <SourceCardGrid />
      </div>
    </div>
  );
}
