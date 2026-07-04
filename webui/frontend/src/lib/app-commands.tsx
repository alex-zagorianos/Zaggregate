import * as React from "react";
import type { LucideIcon } from "lucide-react";

/* A tiny app-level command bus for the Ctrl+K palette.
 *
 * The palette's NAV commands come straight from the tab registry, but tabs also
 * want to contribute ACTION commands that only make sense while they're mounted —
 * e.g. the Inbox's "Update my Inbox now" / "Dismiss all shown" / "Export for AI".
 * Rather than lift all that state up into the palette, a mounted tab registers its
 * commands here (via `useRegisterCommands`) and unregisters on unmount; the palette
 * subscribes and merges them in. Commands are keyed by a stable `id` so a re-render
 * replaces rather than duplicates.
 *
 * This keeps the palette decoupled (it knows nothing about the Inbox) and the tab
 * self-contained (its commands live with its handlers). Not persisted, not routed —
 * purely in-memory for the session. */

export interface AppCommand {
  /** Stable id (dedupe key). */
  id: string;
  /** Palette label, e.g. "Update my Inbox now". */
  label: string;
  icon: LucideIcon;
  run: () => void;
  /** Optional group heading in the palette (defaults to "Actions"). */
  group?: string;
}

type Listener = (commands: AppCommand[]) => void;

const registry = new Map<string, AppCommand>();
const listeners = new Set<Listener>();

function emit() {
  const snapshot = Array.from(registry.values());
  for (const l of listeners) l(snapshot);
}

/** Replace the full set of commands owned by `ownerId`. Any previously-registered
 * command whose id starts with `ownerId + ":"` that is not in `commands` is
 * dropped, so a tab can freely add/remove commands across renders. */
export function setOwnerCommands(
  ownerId: string,
  commands: AppCommand[],
): void {
  const prefix = `${ownerId}:`;
  for (const key of Array.from(registry.keys())) {
    if (key.startsWith(prefix)) registry.delete(key);
  }
  for (const cmd of commands) {
    registry.set(cmd.id.startsWith(prefix) ? cmd.id : `${prefix}${cmd.id}`, {
      ...cmd,
      id: cmd.id.startsWith(prefix) ? cmd.id : `${prefix}${cmd.id}`,
    });
  }
  emit();
}

export function clearOwnerCommands(ownerId: string): void {
  const prefix = `${ownerId}:`;
  let changed = false;
  for (const key of Array.from(registry.keys())) {
    if (key.startsWith(prefix)) {
      registry.delete(key);
      changed = true;
    }
  }
  if (changed) emit();
}

/** Subscribe to the live command set (for the palette). Returns an unsubscribe. */
export function subscribeCommands(listener: Listener): () => void {
  listeners.add(listener);
  listener(Array.from(registry.values()));
  return () => {
    listeners.delete(listener);
  };
}

/** Hook: a tab calls this with its current action commands. Re-registers whenever
 * `commands` changes and clears them on unmount. `ownerId` namespaces the tab's
 * commands so two tabs can't collide. The commands array should be memoized by the
 * caller (stable handler refs) to avoid churn. */
export function useRegisterCommands(
  ownerId: string,
  commands: AppCommand[],
): void {
  React.useEffect(() => {
    setOwnerCommands(ownerId, commands);
    return () => clearOwnerCommands(ownerId);
  }, [ownerId, commands]);
}

/** Hook: the palette subscribes to the current app commands. */
export function useAppCommands(): AppCommand[] {
  const [commands, setCommands] = React.useState<AppCommand[]>(() =>
    Array.from(registry.values()),
  );
  React.useEffect(() => subscribeCommands(setCommands), []);
  return commands;
}
