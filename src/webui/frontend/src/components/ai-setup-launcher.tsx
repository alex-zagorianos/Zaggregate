import * as React from "react";
import { Sparkles } from "lucide-react";

import { useRegisterCommands, type AppCommand } from "@/lib/app-commands";
import { AiSetupDialog } from "@/components/ai-setup-dialog";

/* A global launcher for the AI express-lane dialog + its palette command
 * ("Set up with my AI"). Mounted once in the app shell so the flow is reachable
 * from the Ctrl+K palette at any time (not just during onboarding). Owns the
 * dialog open state; a successful apply just closes it (the mutation already
 * refreshed every view). */

export function AiSetupLauncher() {
  const [open, setOpen] = React.useState(false);

  const commands = React.useMemo<AppCommand[]>(
    () => [
      {
        id: "ai-setup",
        label: "Set up my preferences with AI",
        icon: Sparkles,
        run: () => setOpen(true),
      },
    ],
    [],
  );
  useRegisterCommands("ai-setup", commands);

  return (
    <AiSetupDialog
      open={open}
      onOpenChange={setOpen}
      onApplied={() => setOpen(false)}
    />
  );
}
