import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import "./styles/global.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("Root-Element #root fehlt");
}

/**
 * Query-Client: keine aggressiven Retries (Fehler werden als
 * Fehlerzustand angezeigt), Refetch beim Fokussieren deaktiviert
 * (Operationen-Dashboard: Daten kommen per Intervall/Refetch-Strategie
 * der Hooks).
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 15_000,
    },
  },
});

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
