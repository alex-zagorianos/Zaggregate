import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Sun, Moon, type LucideIcon } from "lucide-react";

import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "@/components/ui/command";
import { TABS, tabCommand } from "@/tabs/registry";
import { useTheme } from "@/lib/theme";
import { filterCommands } from "@/lib/filter-commands";

/* Ctrl+K command palette. Commands = navigate-to-tab (one per registry entry) +
 * toggle-theme. Ranking uses filterCommands (the faithful ui/palette.py port);
 * we disable cmdk's own fuzzy filter (`shouldFilter={false}`) and drive the list
 * ourselves so the ordering matches the desktop app exactly. Phase 1+ can push
 * more commands (e.g. "Run daily") into the `commands` list. */

interface Cmd {
  label: string;
  icon: LucideIcon;
  run: () => void;
}

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const navigate = useNavigate();
  const { mode, toggle } = useTheme();
  const [query, setQuery] = React.useState("");

  React.useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  const commands = React.useMemo<Cmd[]>(() => {
    const navCmds: Cmd[] = TABS.map((tab) => ({
      label: tabCommand(tab),
      icon: tab.icon,
      run: () => navigate(`/${tab.path}`),
    }));
    navCmds.push({
      label: mode === "dark" ? "Toggle light mode" : "Toggle dark mode",
      icon: mode === "dark" ? Sun : Moon,
      run: toggle,
    });
    return navCmds;
  }, [navigate, mode, toggle]);

  const ordered = React.useMemo(() => {
    const byLabel = new Map(commands.map((c) => [c.label, c]));
    return filterCommands(
      commands.map((c) => c.label),
      query,
    )
      .map((l) => byLabel.get(l))
      .filter((c): c is Cmd => Boolean(c));
  }, [commands, query]);

  const runAndClose = (cmd: Cmd) => {
    onOpenChange(false);
    cmd.run();
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} shouldFilter={false}>
      <CommandInput
        placeholder="Type a command or search…"
        value={query}
        onValueChange={setQuery}
      />
      <CommandList>
        <CommandEmpty>No commands found.</CommandEmpty>
        <CommandGroup heading="Commands">
          {ordered.map((cmd) => {
            const Icon = cmd.icon;
            return (
              <CommandItem
                key={cmd.label}
                // value must be unique + we run our own ordering; keep cmdk from
                // re-filtering by giving it the label verbatim.
                value={cmd.label}
                onSelect={() => runAndClose(cmd)}
              >
                <Icon className="size-4" />
                {cmd.label}
              </CommandItem>
            );
          })}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}

/** Global Ctrl+K / Cmd+K listener → toggles the palette. Returns [open, setOpen]. */
export function usePaletteHotkey(): [boolean, (o: boolean) => void] {
  const [open, setOpen] = React.useState(false);
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  return [open, setOpen];
}
