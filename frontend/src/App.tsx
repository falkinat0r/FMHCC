import type { ReactElement } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/layout/AppShell";
import { AuthProvider } from "./features/auth/AuthProvider";
import { RequireAuth } from "./features/auth/RequireAuth";
import LoginPage from "./features/auth/LoginPage";
import OverviewPage from "./features/overview/OverviewPage";
import ComputePage from "./features/compute/ComputePage";
import ResourceDetailPage from "./features/compute/ResourceDetailPage";
import TopologyPage from "./features/topology/TopologyPage";
import MonitoringPage from "./features/monitoring/MonitoringPage";
import IntegrationsPage from "./features/integrations/IntegrationsPage";
import IntegrationDetailPage from "./features/integrations/IntegrationDetailPage";
import AuditPage from "./features/audit/AuditPage";
import SettingsPage from "./features/settings/SettingsPage";

/**
 * Routenplan (R1). Alle Schutzbereiche laufen ueber RequireAuth
 * (Session-Pruefung via GET /api/v1/auth/me) — die serverseitige
 * RBAC bleibt die verbindliche Autorisierung.
 */
export default function App(): ReactElement {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route index element={<OverviewPage />} />
          <Route path="compute" element={<ComputePage />} />
          <Route path="resources/:resourceId" element={<ResourceDetailPage />} />
          <Route path="topology" element={<TopologyPage />} />
          <Route path="monitoring" element={<MonitoringPage />} />
          <Route path="integrations" element={<IntegrationsPage />} />
          <Route
            path="integrations/:integrationId"
            element={<IntegrationDetailPage />}
          />
          <Route path="audit" element={<AuditPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
