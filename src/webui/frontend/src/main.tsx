import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";

import "./index.css";
import { App } from "./App";
import { ThemeProvider, useTheme } from "@/lib/theme";
import { TooltipProvider } from "@/components/ui/tooltip";

/* Provider stack:
 *   BrowserRouter basename="/app"  — Flask serves the SPA under /app
 *   QueryClient                    — TanStack Query (shared cache)
 *   ThemeProvider                  — data-theme + /api/settings/theme sync
 *   TooltipProvider                — Radix tooltip context
 *   Toaster (sonner)               — global toast surface, on-palette
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

/** The sonner Toaster, theme-aware. sonner defaults to a light-only palette
 * unless told otherwise; without this it renders light toasts over a dark UI.
 * Reads the app's own ThemeProvider (data-theme) rather than sonner's separate
 * OS-preference default, so a toast always matches the app's current theme,
 * light or dark, regardless of the OS setting. */
function ThemedToaster() {
  const { mode } = useTheme();
  return (
    <Toaster
      theme={mode}
      position="bottom-right"
      toastOptions={{
        classNames: {
          toast: "!bg-card !text-card-foreground !border-border !rounded-md",
          description: "!text-muted-foreground",
          actionButton: "!bg-primary !text-primary-foreground",
        },
      }}
    />
  );
}

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("#root not found");

createRoot(rootEl).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <TooltipProvider>
          <BrowserRouter basename="/app">
            <App />
          </BrowserRouter>
          <ThemedToaster />
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
);
