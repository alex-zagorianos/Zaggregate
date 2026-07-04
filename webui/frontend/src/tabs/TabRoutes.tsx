import { Routes, Route, Navigate } from "react-router-dom";

import { TABS, DEFAULT_TAB } from "./registry";
import { ComingSoon } from "./ComingSoon";

/* Router: one route per registry tab. `ready` tabs will point at their real
 * component (Phase 1+ swaps `<ComingSoon>` for the tab's element); `ready:false`
 * tabs render the placeholder. Index + unknown paths redirect to the default
 * tab so the SPA fallback (Flask serves index.html for /app/*) lands somewhere
 * sensible. */
export function TabRoutes() {
  return (
    <Routes>
      <Route index element={<Navigate to={`/${DEFAULT_TAB.path}`} replace />} />
      {TABS.map((tab) => (
        <Route
          key={tab.path}
          path={`/${tab.path}`}
          element={<ComingSoon label={tab.label} icon={tab.icon} />}
        />
      ))}
      <Route
        path="*"
        element={<Navigate to={`/${DEFAULT_TAB.path}`} replace />}
      />
    </Routes>
  );
}
