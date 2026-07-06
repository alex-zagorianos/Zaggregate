import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";
import { TABS } from "@/tabs/registry";

/* Horizontal tab strip with an accent underline on the active tab (mirrors the
 * tk Notebook: MUTED idle, ACCENT + bold active). Scrolls horizontally on narrow
 * viewports rather than wrapping. */
export function TabNav() {
  return (
    <nav className="border-border bg-background/60 sticky top-16 z-30 border-b backdrop-blur-sm">
      <div className="mx-auto max-w-[1400px] px-2 sm:px-4">
        {/* Overflow handling: the strip scrolls horizontally on narrow viewports
            (never wraps/clips silently). A fade mask on both edges signals there
            is more to scroll to — verified down to 800px. */}
        <div
          className="scrollbar-none flex items-stretch gap-0.5 overflow-x-auto"
          style={{
            maskImage:
              "linear-gradient(to right, transparent 0, #000 20px, #000 calc(100% - 20px), transparent 100%)",
            WebkitMaskImage:
              "linear-gradient(to right, transparent 0, #000 20px, #000 calc(100% - 20px), transparent 100%)",
          }}
        >
          {TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <NavLink
                key={tab.path}
                to={`/${tab.path}`}
                className={({ isActive }) =>
                  cn(
                    "group relative flex items-center gap-2 whitespace-nowrap px-4 py-3 text-sm font-medium transition-colors duration-150",
                    "outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset",
                    isActive
                      ? "text-primary"
                      : "text-muted-foreground hover:text-foreground",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon
                      className={cn(
                        "size-4 transition-opacity",
                        isActive ? "opacity-100" : "opacity-70",
                      )}
                    />
                    {tab.label}
                    <span
                      className={cn(
                        "absolute inset-x-2 -bottom-px h-0.5 rounded-full transition-all duration-150",
                        isActive
                          ? "bg-primary opacity-100"
                          : "bg-primary opacity-0 group-hover:opacity-30",
                      )}
                    />
                  </>
                )}
              </NavLink>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
