import { lazy, Suspense, type ComponentType, type ReactNode } from "react";
import { Routes, Route, Navigate } from "react-router-dom";

import { TABS, DEFAULT_TAB } from "./registry";
import { ComingSoon } from "./ComingSoon";
import { InboxTab } from "./inbox/InboxTab";
import { LoadingState } from "@/components/states";

/* Router: one route per registry tab. `ready` tabs render their real component;
 * `ready:false` tabs render the ComingSoon placeholder. Index + unknown paths
 * redirect to the default tab so the SPA fallback (Flask serves index.html for
 * /app/*) lands somewhere sensible.
 *
 * Code-splitting: every non-default tab is a React.lazy() import, each its own
 * chunk fetched only when its route is visited. The Suspense fallback (shared
 * LoadingState) covers the brief gap while a tab chunk downloads. Inbox — the
 * DEFAULT tab — stays a normal eager import so first paint never shows a lazy
 * flash. */

// Lazy component refs for the tabs whose web twin has shipped, keyed by path.
// Inbox is eager (see import above) since it's DEFAULT_TAB and always needed
// on first paint.
const READY_COMPONENTS: Record<string, ComponentType> = {
  inbox: InboxTab,
  "top-picks": lazy(() =>
    import("./toppicks/TopPicksTab").then((m) => ({ default: m.TopPicksTab })),
  ),
  sources: lazy(() =>
    import("./sources/SourcesTab").then((m) => ({ default: m.SourcesTab })),
  ),
  tracker: lazy(() =>
    import("./tracker/TrackerTab").then((m) => ({ default: m.TrackerTab })),
  ),
  board: lazy(() =>
    import("./board/BoardTab").then((m) => ({ default: m.BoardTab })),
  ),
  insights: lazy(() =>
    import("./insights/InsightsTab").then((m) => ({
      default: m.InsightsTab,
    })),
  ),
  search: lazy(() =>
    import("./search/SearchTab").then((m) => ({ default: m.SearchTab })),
  ),
  "apply-queue": lazy(() =>
    import("./queue/ApplyQueueTab").then((m) => ({
      default: m.ApplyQueueTab,
    })),
  ),
  resume: lazy(() =>
    import("./resume/ResumeTab").then((m) => ({ default: m.ResumeTab })),
  ),
  guide: lazy(() =>
    import("./guide/GuideTab").then((m) => ({ default: m.GuideTab })),
  ),
  // EXPERIMENTAL (S36c)
  discover: lazy(() =>
    import("./discover/DiscoverTab").then((m) => ({
      default: m.DiscoverTab,
    })),
  ),
};

function readyElement(path: string): ReactNode {
  const Cmp = READY_COMPONENTS[path];
  return Cmp ? <Cmp /> : null;
}

export function TabRoutes() {
  return (
    <Suspense fallback={<LoadingState />}>
      <Routes>
        <Route
          index
          element={<Navigate to={`/${DEFAULT_TAB.path}`} replace />}
        />
        {TABS.map((tab) => (
          <Route
            key={tab.path}
            path={`/${tab.path}`}
            element={
              tab.ready && READY_COMPONENTS[tab.path] ? (
                readyElement(tab.path)
              ) : (
                <ComingSoon label={tab.label} icon={tab.icon} />
              )
            }
          />
        ))}
        <Route
          path="*"
          element={<Navigate to={`/${DEFAULT_TAB.path}`} replace />}
        />
      </Routes>
    </Suspense>
  );
}
