import { useEffect, useState, type ReactElement, type ReactNode } from "react";

import {
  api,
  ApiRequestError,
  type CurrentUserResponse,
  type IntegrationOut,
  type Paged,
  type ResourceOut,
} from "../api/client";

interface DashboardProps {
  user: CurrentUserResponse;
  onLoggedOut: () => Promise<void> | void;
}

interface PanelData<T> {
  state: "loading" | "ready" | "error";
  data?: Paged<T>;
  error?: string;
}

/**
 * R0-Dashboard-Shell: leeres Grundgeruest mit echten v1-Listen
 * (Integrationen + Ressourcen). Leere Listen sind ehrlich "keine
 * konfiguriert" — keine Fixtures, keine Zufallswerte.
 */
export default function Dashboard({ user, onLoggedOut }: DashboardProps): ReactElement {
  const [integrations, setIntegrations] = useState<PanelData<IntegrationOut>>({ state: "loading" });
  const [resources, setResources] = useState<PanelData<ResourceOut>>({ state: "loading" });

  useEffect(() => {
    let cancelled = false;
    api
      .get<Paged<IntegrationOut>>("/integrations")
      .then((data) => {
        if (!cancelled) setIntegrations({ state: "ready", data });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setIntegrations({ state: "error", error: describe(err) });
        }
      });
    api
      .get<Paged<ResourceOut>>("/resources")
      .then((data) => {
        if (!cancelled) setResources({ state: "ready", data });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setResources({ state: "error", error: describe(err) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleLogout(): Promise<void> {
    try {
      await api.post("/auth/logout");
    } catch {
      // Logout-Fehler darf die UI nicht blockieren: Session wird neu geprueft.
    }
    await onLoggedOut();
  }

  return (
    <div className="layout">
      <header className="topbar">
        <div>
          <span className="brand">HCC</span>
          <span className="muted">— Homelab Control Center</span>
        </div>
        <div className="topbar-user">
          <span>
            {user.username} <span className="muted">({user.role})</span>
          </span>
          <button onClick={() => void handleLogout()}>Abmelden</button>
        </div>
      </header>

      <main className="content">
        <section className="card panel">
          <h2>Integrationen</h2>
          <Panel<IntegrationOut>
            panel={integrations}
            emptyText="Noch keine Integrationen konfiguriert."
            renderItem={(item) => (
              <li key={item.id}>
                <strong>{item.name}</strong>{" "}
                <span className="muted">
                  [{item.integration_id}] adapter={item.adapter} status={item.status}
                </span>
                {item.last_error !== null && <span className="error"> {item.last_error}</span>}
              </li>
            )}
          />
        </section>

        <section className="card panel">
          <h2>Ressourcen (Inventar)</h2>
          <Panel<ResourceOut>
            panel={resources}
            emptyText="Noch keine Ressourcen erkannt."
            renderItem={(item) => (
              <li key={item.id}>
                <strong>{item.name ?? item.external_id}</strong>{" "}
                <span className="muted">
                  [{item.resource_type}] status={item.status} source={item.source}
                </span>
              </li>
            )}
          />
        </section>
      </main>
    </div>
  );
}

function describe(err: unknown): string {
  if (err instanceof ApiRequestError) {
    return `${err.message} (code ${err.code})`;
  }
  return "Unerwarteter Fehler";
}

function Panel<T>({
  panel,
  emptyText,
  renderItem,
}: {
  panel: PanelData<T>;
  emptyText: string;
  renderItem: (item: T) => ReactNode;
}): ReactElement {
  if (panel.state === "loading") {
    return <p className="muted">Wird geladen…</p>;
  }
  if (panel.state === "error") {
    return <p className="error" role="alert">{panel.error}</p>;
  }
  if (panel.data === undefined || panel.data.items.length === 0) {
    return <p className="muted">{emptyText}</p>;
  }
  return (
    <>
      <ul className="list">
        {panel.data.items.map(renderItem)}
      </ul>
      <p className="muted pageinfo">
        {panel.data.total} gesamt · Seite {panel.data.page}/{panel.data.total_pages}
      </p>
    </>
  );
}
