import type { ReactNode } from "react";
import { Routes, Route, Navigate } from "react-router-dom";

import { TABS, DEFAULT_TAB } from "./registry";
import { ComingSoon } from "./ComingSoon";
import { InboxTab } from "./inbox/InboxTab";
import { TopPicksTab } from "./toppicks/TopPicksTab";
import { SourcesTab } from "./sources/SourcesTab";
import { TrackerTab } from "./tracker/TrackerTab";
import { BoardTab } from "./board/BoardTab";

/* Router: one route per registry tab. `ready` tabs render their real component;
 * `ready:false` tabs render the ComingSoon placeholder. Index + unknown paths
 * redirect to the default tab so the SPA fallback (Flask serves index.html for
 * /app/*) lands somewhere sensible. */

// Real components for the tabs whose web twin has shipped, keyed by path.
const READY_ELEMENTS: Record<string, ReactNode> = {
  inbox: <InboxTab />,
  "top-picks": <TopPicksTab />,
  sources: <SourcesTab />,
  tracker: <TrackerTab />,
  board: <BoardTab />,
};

export function TabRoutes() {
  return (
    <Routes>
      <Route index element={<Navigate to={`/${DEFAULT_TAB.path}`} replace />} />
      {TABS.map((tab) => (
        <Route
          key={tab.path}
          path={`/${tab.path}`}
          element={
            tab.ready && READY_ELEMENTS[tab.path] ? (
              READY_ELEMENTS[tab.path]
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
  );
}
