import type { Role } from "../api/types";

/**
 * RBAC-Hinweise fuer die UI (frozen Model: viewer < operator < admin).
 *
 * WICHTIG: Die serverseitige Pruefung ist die einzige verbindliche
 * Autorisierung. Diese Helfer steuern nur die Darstellungslogik
 * (Buttons zeigen/verbergen/deaktivieren) — niemals umgekehrt.
 */

const ROLE_LEVEL: Record<Role, number> = {
  viewer: 0,
  operator: 1,
  admin: 2,
};

/** true, wenn `role` mindestens die geforderte Stufe hat. */
export function hasRole(role: Role | null | undefined, required: Role): boolean {
  if (role === null || role === undefined) return false;
  return ROLE_LEVEL[role] >= ROLE_LEVEL[required];
}

/** viewer+ darf Integrationen/Ressourcen lesen. */
export function canReadInfra(role: Role | null | undefined): boolean {
  return hasRole(role, "viewer");
}

/** operator+ darf Verwaltungsaktionen ausloesen (z. B. VM-Start). */
export function canOperate(role: Role | null | undefined): boolean {
  return hasRole(role, "operator");
}

/** admin darf Integrationen/Users verwalten, Audit lesen. */
export function canAdmin(role: Role | null | undefined): boolean {
  return hasRole(role, "admin");
}

export const ROLE_LABEL: Record<Role, string> = {
  viewer: "Viewer (nur Lesezugriff)",
  operator: "Operator (Lesen + Aktionen)",
  admin: "Admin (Vollzugriff)",
};
