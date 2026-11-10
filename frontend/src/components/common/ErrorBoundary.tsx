import { Component, type ErrorInfo, type ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Wird beim "Zurueck"-Knopf aufgerufen (typisch: Navigation nach /) */
  onReset?: () => void;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * App-weite Fehlergrenze. Zeigt den Fehler an, statt die gesamte
 * SPA wegzucrashen; "Zurueck" setzt den Zustand und navigiert.
 */
export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Kein PII/Secrets in der Konsole — nur technischer Kontext.
    console.error("ErrorBoundary:", error.message, info.componentStack);
  }

  handleReset = (): void => {
    this.setState({ error: null });
    this.props.onReset?.();
  };

  render(): ReactNode {
    if (this.state.error === null) return this.props.children;
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-3 p-6 text-center">
        <h1 className="text-lg font-semibold">Unerwarteter Fehler</h1>
        <p className="max-w-md text-sm text-muted-foreground">
          {this.state.error.message}
        </p>
        <p className="text-xs text-muted-foreground">
          Die Ansicht wurde nicht geladen. Bitte zurueck navigieren oder die
          Seite neu laden.
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground"
            onClick={this.handleReset}
          >
            Zurueck
          </button>
          <button
            type="button"
            className="rounded-md border border-border px-4 py-2 text-sm"
            onClick={() => window.location.assign("/")}
          >
            Neu laden
          </button>
        </div>
      </main>
    );
  }
}
