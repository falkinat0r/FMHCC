import type { LucideIcon } from "lucide-react";
import {
  Activity,
  Cpu,
  LayoutDashboard,
  Network,
  PlugZap,
  ScrollText,
  Settings,
} from "lucide-react";

export interface NavItem {
  readonly to: string;
  readonly label: string;
  readonly icon: LucideIcon;
  readonly adminOnly?: boolean;
}

export interface NavSection {
  readonly title: string;
  readonly items: readonly NavItem[];
}

/**
 * Navigation (klare Hierarchie, Desktop-first, responsiv).
 * RBAC: Audit nur fuer admin (serverseitig geprueft, UI zeigt es nur
 * dort an, wo es lesbar ist — docs/api-contracts.md §4).
 */
export const NAV_SECTIONS: readonly NavSection[] = [
  {
    title: "Überblick",
    items: [{ to: "/", label: "Dashboard", icon: LayoutDashboard }],
  },
  {
    title: "Infrastruktur",
    items: [
      { to: "/compute", label: "Compute", icon: Cpu },
      { to: "/topology", label: "Topologie", icon: Network },
    ],
  },
  {
    title: "Betrieb",
    items: [{ to: "/monitoring", label: "Monitoring", icon: Activity }],
  },
  {
    title: "Verwaltung",
    items: [
      { to: "/integrations", label: "Integrationen", icon: PlugZap },
      { to: "/audit", label: "Audit-Log", icon: ScrollText, adminOnly: true },
      { to: "/settings", label: "Einstellungen", icon: Settings },
    ],
  },
];

/** Alle (auch admin-only) Nav-Eintraege — fuer Breadcrumbs/Tests. */
export const ALL_NAV_ITEMS: readonly NavItem[] = NAV_SECTIONS.flatMap(
  (s) => s.items,
);
