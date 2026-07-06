import * as React from "react";
import {
  Sun,
  Moon,
  FolderOpen,
  ChevronDown,
  Command as CommandIcon,
  Plus,
} from "lucide-react";

import { ZagMark } from "./zag-mark";
import { SettingsMenu } from "./settings-menu";
import { NewProjectDialog } from "./new-project-dialog";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { useTheme } from "@/lib/theme";
import { useProjects, useSwitchProject } from "@/api/queries";
import { isMac } from "@/lib/platform";

/* The brand hero — mirrors ui/topbar.py: zag mark + "Zag" (accent) "gregate"
 * (ink) wordmark in Fraunces + the "find · rank · apply" tagline. Right side:
 * project switcher (GET/POST /api/project), Ctrl+K hint, theme toggle. */

function Wordmark() {
  return (
    <div className="flex items-center gap-2.5 select-none">
      <ZagMark className="text-primary size-8" />
      <div className="flex items-baseline gap-0">
        <span className="zg-serif text-primary text-[1.7rem] leading-none font-semibold tracking-tight">
          Zag
        </span>
        <span className="zg-serif text-foreground text-[1.7rem] leading-none font-semibold tracking-tight">
          gregate
        </span>
        <span className="text-muted-foreground ml-3 hidden text-xs tracking-wide sm:inline">
          find · rank · apply
        </span>
      </div>
    </div>
  );
}

function ProjectSwitcher() {
  const { data } = useProjects();
  const switchProject = useSwitchProject();
  const [newOpen, setNewOpen] = React.useState(false);
  const active = data?.active ?? "";
  const projects = data?.projects ?? [];
  const activeName =
    projects.find((p) => p.slug === active)?.name || active || "No project";

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="max-w-[13rem] gap-1.5"
            disabled={switchProject.isPending}
          >
            <FolderOpen className="size-3.5 opacity-70" />
            <span className="truncate">{activeName}</span>
            <ChevronDown className="size-3.5 opacity-60" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[14rem]">
          <DropdownMenuLabel>Project</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {projects.length === 0 && (
            <DropdownMenuItem disabled>No projects yet</DropdownMenuItem>
          )}
          {projects.map((p) => (
            <DropdownMenuItem
              key={p.slug}
              onSelect={() => {
                if (p.slug !== active) switchProject.mutate(p.slug);
              }}
              className="flex flex-col items-start gap-0.5"
            >
              <span className="flex w-full items-center gap-2">
                <span className="truncate">{p.name}</span>
                {p.slug === active && (
                  <span className="text-primary ml-auto text-xs">active</span>
                )}
              </span>
              {p.person && (
                <span className="text-muted-foreground text-xs">
                  {p.person}
                </span>
              )}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setNewOpen(true)} className="gap-2">
            <Plus className="size-3.5 opacity-70" />
            New project…
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <NewProjectDialog
        open={newOpen}
        onOpenChange={setNewOpen}
        existingSlugs={projects.map((p) => p.slug)}
      />
    </>
  );
}

export function Topbar({ onOpenPalette }: { onOpenPalette: () => void }) {
  const { mode, toggle } = useTheme();
  const mac = isMac();
  return (
    <header className="border-border bg-card/80 sticky top-0 z-40 border-b backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-[1400px] items-center gap-4 px-4 sm:px-6">
        <Wordmark />
        <div className="ml-auto flex items-center gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="text-muted-foreground hidden gap-1.5 md:inline-flex"
                onClick={onOpenPalette}
              >
                {/* Platform-correct hint: the lucide Command icon IS the ⌘
                    glyph, so it may only show on a Mac. Windows/Linux get plain
                    "Ctrl K" with no glyph (the Phase-0 gate flagged the ⌘ showing
                    on Windows). */}
                {mac ? (
                  <>
                    <CommandIcon className="size-3.5" />
                    <span className="zg-num text-xs">K</span>
                  </>
                ) : (
                  <span className="zg-num text-xs">Ctrl K</span>
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>Command palette</TooltipContent>
          </Tooltip>

          <ProjectSwitcher />

          <SettingsMenu />

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={toggle}
                aria-label={
                  mode === "dark"
                    ? "Switch to light mode"
                    : "Switch to dark mode"
                }
              >
                {mode === "dark" ? (
                  <Sun className="size-4" />
                ) : (
                  <Moon className="size-4" />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {mode === "dark" ? "Light mode" : "Dark mode"}
            </TooltipContent>
          </Tooltip>
        </div>
      </div>
    </header>
  );
}
