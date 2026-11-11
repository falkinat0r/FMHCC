/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Gekennzeichneter Entwicklungsmodus: wenn "true", liefern die
   * Datenquellen ausschließlich klar markierte Test-Fixtures
   * (docs/agent-reports/R1-frontend.md). Niemals in Produktion aktivieren.
   */
  readonly VITE_HCC_DEV_FIXTURE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
