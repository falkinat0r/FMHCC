/**
 * Typ-Aliase auf die generierten OpenAPI-Typen
 * (`src/api/generated/schema.ts`, per `npm run gen:types` aus dem
 * frozen Contract-Snapshot erzeugt).
 *
 * Die generierten Typen sind Agent-2-seitig NUR LESBAR
 * (docs/api-contracts.md §7) — Abweichungen nur via Proposal.
 */
import type { components } from "./generated/schema";

type Schemas = components["schemas"];

export type Role = Schemas["Role"];
export type CurrentUserResponse = Schemas["CurrentUserResponse"];
export type LoginResponse = Schemas["LoginResponse"];
export type LogoutResponse = Schemas["LogoutResponse"];
export type BootstrapRequest = Schemas["BootstrapRequest"];
export type BootstrapResponse = Schemas["BootstrapResponse"];

export type UserOut = Schemas["UserOut"];
export type UserCreate = Schemas["UserCreate"];
export type UserUpdate = Schemas["UserUpdate"];

export type AdapterKind = Schemas["AdapterKind"];
export type IntegrationOut = Schemas["IntegrationOut"];
export type IntegrationCreate = Schemas["IntegrationCreate"];
export type VerifyResponse = Schemas["VerifyResponse"];
export type VerifyStatus = Schemas["VerifyStatus"];

export type ResourceStatus = Schemas["ResourceStatus"];
export type ResourceType = Schemas["ResourceType"];
export type ResourceSource = Schemas["ResourceSource"];
export type ResourceOut = Schemas["ResourceOut"];
export type ResourceDetailOut = Schemas["ResourceDetailOut"];
export type ResourceRelationOut = Schemas["ResourceRelationOut"];

export type AuditEventOut = Schemas["AuditEventOut"];

export type HealthStatus = Schemas["HealthStatus"];
export type LiveHealthResponse = Schemas["LiveHealthResponse"];
export type ReadyHealthResponse = Schemas["ReadyHealthResponse"];
export type VersionResponse = Schemas["VersionResponse"];
export type ErrorCode = Schemas["ErrorCode"];

/** Einheitliche Paging-Envelope (frozen Contract). */
export interface Paged<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}
