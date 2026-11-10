import { useState } from "react";
import { Outlet } from "react-router-dom";

import { isDevFixture } from "../../api/dev";
import { DevBanner } from "../common/DevBanner";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

/**
 * App-Shell: Sidebar (Desktop, responsiv als Drawer auf Mobilgeraeten),
 * Header, Content-Outlet. Skip-Link fuer Tastatur-Nutzer.
 */
export function AppShell() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main-content"
        className="sr-only rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50"
      >
        Zum Inhalt springen
      </a>
      {isDevFixture() && <DevBanner />}
      <div className="flex flex-1">
        {/* Desktop-Sidebar */}
        <div className="hidden md:block">
          <Sidebar />
        </div>
        {/* Mobile-Drawer */}
        {mobileNavOpen && (
          <div className="fixed inset-0 z-40 md:hidden">
            <button
              type="button"
              aria-label="Navigation schliessen"
              className="absolute inset-0 bg-black/60"
              onClick={() => setMobileNavOpen(false)}
              tabIndex={-1}
            />
            <div className="absolute inset-y-0 left-0">
              <Sidebar className="h-full shadow-xl" />
            </div>
          </div>
        )}
        <div className="flex min-w-0 flex-1 flex-col">
          <Header
            onToggleSidebar={() => setMobileNavOpen((v) => !v)}
          />
          <main id="main-content" className="flex-1 p-4 lg:p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}

