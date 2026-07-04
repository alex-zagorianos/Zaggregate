import type { LucideIcon } from "lucide-react";
import {
  Inbox,
  Star,
  Search,
  ClipboardList,
  ListChecks,
  KanbanSquare,
  FileText,
  BookOpen,
  PlugZap,
} from "lucide-react";

/* THE tab registry — single source of truth for nav order, routing, icons, and
 * palette commands. To ADD a tab (Phase 1+):
 *   1. Add an entry here (path, label, icon, `ready: true`, and a `element`
 *      importer once the tab component exists).
 *   2. That's it — TabNav, the router, and the Ctrl+K palette all read this list.
 * A tab with `ready: false` renders the ComingSoon empty state automatically.
 */

export interface TabDef {
  /** URL segment under /app (react-router). "" is the index (Inbox). */
  path: string;
  /** Nav + palette label. */
  label: string;
  /** Palette command text ("Go to <label>") — overridable. */
  command?: string;
  icon: LucideIcon;
  /** false → renders the ComingSoon placeholder (still in the desktop app). */
  ready: boolean;
}

export const TABS: readonly TabDef[] = [
  {
    path: "inbox",
    label: "Inbox",
    command: "Go to Inbox",
    icon: Inbox,
    ready: true,
  },
  { path: "top-picks", label: "Top Picks", icon: Star, ready: true },
  {
    path: "search",
    label: "Search",
    command: "Search for jobs",
    icon: Search,
    ready: true,
  },
  {
    path: "apply-queue",
    label: "Apply Queue",
    icon: ClipboardList,
    ready: true,
  },
  { path: "tracker", label: "Tracker", icon: ListChecks, ready: true },
  { path: "board", label: "Board", icon: KanbanSquare, ready: true },
  { path: "resume", label: "Resume", icon: FileText, ready: true },
  { path: "guide", label: "Guide", icon: BookOpen, ready: true },
  {
    path: "sources",
    label: "Sources",
    command: "Connect job sources",
    icon: PlugZap,
    ready: true,
  },
] as const;

/** The default landing tab. */
export const DEFAULT_TAB = TABS[0];

export function tabCommand(tab: TabDef): string {
  return tab.command ?? `Go to ${tab.label}`;
}
