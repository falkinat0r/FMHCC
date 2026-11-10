import type { AdapterKind } from "../../api/types";

/**
 * Statische Beschreibung pro Adapter (frozen Enum AdapterKind).
 *
 * Diese Texte dokumentieren, was die jeweilige Anbindung in HCC
 * leisten KANN — die tatsaechlich verfuegbaren Funktionen werden
 * pro Integration ueber das `capabilities`-Feld der API angezeigt
 * (kein raten). Prometheus und Grafana laufen ueber den
 * "monitoring"-Adapter (frozen Enum-Design).
 */
export interface AdapterInfo {
  readonly label: string;
  readonly summary: string;
}

export const ADAPTER_INFO: Record<AdapterKind, AdapterInfo> = {
  proxmox: {
    label: "Proxmox VE",
    summary:
      "Physische Hosts, Proxmox-Nodes, VMs (QEMU), LXC-Container, Storage und — sobald freigegeben — VM-/LXC-Aktionen (start, sanftes shutdown, reboot).",
  },
  truenas: {
    label: "TrueNAS",
    summary:
      "Pools, Datasets, Kapazitaet und Zustand (read-only; Scrub/SMART je nach API-Version).",
  },
  pihole: {
    label: "Pi-hole",
    summary:
      "DNS-Block-Statistiken und Gravuren (mehrere Instanzen; versions-/API-kompatibel).",
  },
  tailscale: {
    label: "Tailscale",
    summary:
      "Tailnet-Knoten und Erreichbarkeit (Control-Plane und Local-Client-Schnittstellen werden getrennt ausgelesen).",
  },
  docker: {
    label: "Docker",
    summary:
      "Container-Status auf Docker-Hosts (Remote-API nur ueber sicher transportierte Authentifizierung, niemals offenen TCP-Socket).",
  },
  monitoring: {
    label: "Monitoring (Prometheus / Grafana)",
    summary:
      "Bestehende Prometheus-/Grafana-Instanzen; Metriken und Dashboards. Im R0-Vertrag noch ohne Metrik-Endpunkt (Proposal: frontend-metrics-and-alerts).",
  },
  homeassistant: {
    label: "Home Assistant",
    summary: "Optionale read-only-Anbindung an Home Assistant.",
  },
  unknown: {
    label: "Unbekannter Adapter",
    summary: "Adapter ist nicht bekannt — Funktionen nicht ermittelbar.",
  },
};

export function adapterInfo(kind: string): AdapterInfo {
  return (
    ADAPTER_INFO[kind as AdapterKind] ?? {
      label: kind || "Unbekannt",
      summary: "Adapter ist nicht bekannt — Funktionen nicht ermittelbar.",
    }
  );
}
