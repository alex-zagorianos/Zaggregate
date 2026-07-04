import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";

import "./index.css";
import { App } from "./App";
import { ThemeProvider } from "@/lib/theme";
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
          <Toaster
            position="bottom-right"
            toastOptions={{
              classNames: {
                toast:
                  "!bg-card !text-card-foreground !border-border !rounded-md",
                description: "!text-muted-foreground",
                actionButton: "!bg-primary !text-primary-foreground",
              },
            }}
          />
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
);
