import * as React from "react";
import { Building2, ListPlus, MapPin } from "lucide-react";

import { useRegisterCommands, type AppCommand } from "@/lib/app-commands";
import { AddCompaniesDialog } from "./AddCompaniesDialog";
import { BuildListDialog } from "./BuildListDialog";
import { SeedAreaDialog } from "./SeedAreaDialog";

/* A single mount point for the three company flows (Add / Build / Seed) that owns
 * their dialog state, registers the palette commands, and exposes an imperative
 * open API via context so any tab's buttons (the Search tab's "+ Add Companies" /
 * "Build My List", a future Tools menu) can trigger them without threading state.
 *
 * Mounted once at the app shell (like the palette) so the dialogs are available
 * app-wide and the palette commands persist regardless of the active tab. */

type Flow = "add" | "build" | "seed";

interface CompaniesFlowsApi {
  open: (flow: Flow) => void;
}

const Ctx = React.createContext<CompaniesFlowsApi | null>(null);

/** Access the companies-flow opener. Safe to call from any component under the
 * provider; returns a no-op opener if somehow used outside (defensive). */
export function useCompaniesFlows(): CompaniesFlowsApi {
  const ctx = React.useContext(Ctx);
  return ctx ?? { open: () => {} };
}

export function CompaniesFlowsProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [add, setAdd] = React.useState(false);
  const [build, setBuild] = React.useState(false);
  const [seed, setSeed] = React.useState(false);

  const api = React.useMemo<CompaniesFlowsApi>(
    () => ({
      open: (flow) => {
        if (flow === "add") setAdd(true);
        else if (flow === "build") setBuild(true);
        else setSeed(true);
      },
    }),
    [],
  );

  const commands = React.useMemo<AppCommand[]>(
    () => [
      {
        id: "add-companies",
        label: "Add companies",
        icon: Building2,
        run: () => setAdd(true),
      },
      {
        id: "build-list",
        label: "Build my company list",
        icon: ListPlus,
        run: () => setBuild(true),
      },
      {
        id: "seed-area",
        label: "Seed my area",
        icon: MapPin,
        run: () => setSeed(true),
      },
    ],
    [],
  );
  useRegisterCommands("companies", commands);

  return (
    <Ctx.Provider value={api}>
      {children}
      <AddCompaniesDialog open={add} onOpenChange={setAdd} />
      <BuildListDialog open={build} onOpenChange={setBuild} />
      <SeedAreaDialog open={seed} onOpenChange={setSeed} />
    </Ctx.Provider>
  );
}
