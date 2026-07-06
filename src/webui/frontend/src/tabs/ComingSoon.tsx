import type { LucideIcon } from "lucide-react";
import { EmptyState } from "@/components/states";

/* The placeholder every not-yet-built tab shows. Deliberately elegant (not a
 * "404") — it frames the web UI as an in-progress twin of the desktop app, per
 * the plan's "coming soon — still in the desktop app" guidance. */
export function ComingSoon({
  label,
  icon,
}: {
  label: string;
  icon: LucideIcon;
}) {
  return (
    <EmptyState
      icon={icon}
      title={`${label} — coming soon`}
      message={`This tab is being rebuilt for the web. For now, ${label} lives in the desktop app. Each tab lands here as its web twin is signed off.`}
    />
  );
}
