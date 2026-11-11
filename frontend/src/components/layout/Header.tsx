import { Menu } from "lucide-react";

import { Button } from "../ui/button";
import { Breadcrumbs } from "./Breadcrumbs";
import { GlobalSearch } from "./GlobalSearch";
import { UserMenu } from "./UserMenu";

interface HeaderProps {
  /** Mobile: Sidebar ein-/ausblenden */
  onToggleSidebar: () => void;
}

/**
 * Top-Header: Mobile-Nav-Toggle, Breadcrumbs, globale Suche,
 * Benutzerbereich.
 */
export function Header({ onToggleSidebar }: HeaderProps) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-card px-3 lg:px-4">
      <Button
        variant="ghost"
        size="icon"
        className="md:hidden"
        aria-label="Navigation ein-/ausblenden"
        aria-expanded="false"
        onClick={onToggleSidebar}
      >
        <Menu className="h-4 w-4" aria-hidden="true" />
      </Button>

      <Breadcrumbs />

      <div className="ml-auto flex flex-1 items-center justify-end gap-3 md:flex-none">
        <GlobalSearch />
        <UserMenu />
      </div>
    </header>
  );
}
