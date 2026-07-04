import { Topbar } from "@/components/topbar";
import { TabNav } from "@/components/tab-nav";
import { CommandPalette, usePaletteHotkey } from "@/components/command-palette";
import { TabRoutes } from "@/tabs/TabRoutes";

/* The app shell: sticky brand topbar + tab nav, a scrolling content region that
 * the router fills, and the global Ctrl+K palette. The 8px grid + generous
 * whitespace live in the max-width content column. */
export function App() {
  const [paletteOpen, setPaletteOpen] = usePaletteHotkey();

  return (
    <div className="relative z-10 flex min-h-screen flex-col">
      <Topbar onOpenPalette={() => setPaletteOpen(true)} />
      <TabNav />
      <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 sm:px-6 sm:py-8">
        <TabRoutes />
      </main>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  );
}
