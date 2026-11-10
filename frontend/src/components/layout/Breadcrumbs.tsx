import { Fragment } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronRight, Home } from "lucide-react";

const SECTION_LABELS: Record<string, string> = {
  compute: "Compute",
  topology: "Topologie",
  monitoring: "Monitoring",
  integrations: "Integrationen",
  audit: "Audit-Log",
  settings: "Einstellungen",
  resources: "Ressourcen",
};

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Breadcrumbs aus dem aktiven Pfad (statische Karten, keine
 * erfunbenen Seiten). UUID-Segmente werden nicht als
 * Breadcrumb angezeigt (die Detail-Seite zeigt den Namen).
 */
export function Breadcrumbs() {
  const { pathname } = useLocation();
  const segments = pathname.split("/").filter(Boolean);

  const parts: { label: string; to: string }[] = [];
  if (segments.length === 0) {
    parts.push({ label: "Dashboard", to: "/" });
  } else {
    const first = segments[0] ?? "";
    parts.push({
      label: SECTION_LABELS[first] ?? first,
      to: `/${first}`,
    });
    for (let i = 1; i < segments.length; i += 1) {
      const segment = segments[i];
      if (segment === undefined || UUID_RE.test(segment)) continue;
      parts.push({ label: segment, to: `/${segments.slice(0, i + 1).join("/")}` });
    }
  }

  const last = parts.length > 0 ? parts[parts.length - 1] : undefined;

  return (
    <nav aria-label="Breadcrumbs" className="hidden min-w-0 md:block">
      <ol className="flex min-w-0 items-center gap-1 text-xs text-muted-foreground">
        <li className="shrink-0">
          <Link
            to="/"
            aria-label="Dashboard"
            className="rounded p-1 hover:bg-accent hover:text-foreground"
          >
            <Home className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </li>
        {parts.map((part) => (
          <Fragment key={part.to}>
            <ChevronRight
              className="h-3 w-3 shrink-0"
              aria-hidden="true"
            />
            <li
              className="truncate"
              aria-current={part === last ? "page" : undefined}
            >
              {part === last ? (
                <span className="text-foreground">{part.label}</span>
              ) : (
                <Link
                  to={part.to}
                  className="hover:text-foreground hover:underline"
                >
                  {part.label}
                </Link>
              )}
            </li>
          </Fragment>
        ))}
      </ol>
    </nav>
  );
}
