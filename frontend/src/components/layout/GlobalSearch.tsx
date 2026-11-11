import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";

import { isDevFixture } from "../../api/dev";
import { useResources } from "../../api/query";
import { cn } from "../../lib/cn";
import { Input } from "../ui/input";
import { StatusBadge } from "../common/StatusBadge";

/**
 * Globale Suche: durchsucht das Inventar (GET /api/v1/resources?q=…)
 * mit 300 ms Debounce. Keyboard: Pfeiltasten, Enter (Erstes Treffer),
 * Escape schliesst. Ergebnisliste ist eine ARIA-Listbox.
 */
export function GlobalSearch() {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);

  const trimmed = query.trim();
  const { data, isPending } = useResources({
    q: trimmed.length >= 2 ? trimmed : null,
    page: 1,
    pageSize: 8,
  });

  const results = data?.items ?? [];

  // Debounce: bei < 2 Zeichen nicht suchen (Fixtures-Modus inklusive)
  useEffect(() => {
    if (trimmed.length < 2) return;
    const handle = setTimeout(() => setOpen(true), 300);
    return () => clearTimeout(handle);
  }, [trimmed]);

  useEffect(() => {
    setActive(0);
  }, [data]);

  function close(): void {
    setOpen(false);
  }

  function select(id: string): void {
    close();
    setQuery("");
    navigate(`/resources/${id}`);
  }

  return (
    <div className="relative w-full max-w-xs">
      <label htmlFor="global-search" className="sr-only">
        Ressourcen durchsuchen
      </label>
      <Search
        className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground"
        aria-hidden="true"
      />
      <Input
        ref={inputRef}
        id="global-search"
        role="combobox"
        aria-expanded={open}
        aria-controls="global-search-listbox"
        aria-autocomplete="list"
        className="pl-8"
        placeholder="Suchen (Name, ID)…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => {
          if (trimmed.length >= 2) setOpen(true);
        }}
        onBlur={() => setTimeout(close, 150)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            close();
            inputRef.current?.blur();
          } else if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(a + 1, Math.max(0, results.length - 1)));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            const item = results[active];
            if (item) select(item.id);
          }
        }}
      />
      {open && trimmed.length >= 2 && (
        <ul
          id="global-search-listbox"
          role="listbox"
          aria-label="Suchergebnisse"
          className="absolute z-40 mt-1 w-full overflow-hidden rounded-md border border-border bg-popover shadow-lg"
        >
          {isPending && (
            <li className="p-3 text-xs text-muted-foreground">Suche…</li>
          )}
          {!isPending && results.length === 0 && (
            <li className="p-3 text-xs text-muted-foreground">
              Keine Treffer
              {isDevFixture() ? " (Fixtures-Modus)" : ""}
            </li>
          )}
          {!isPending &&
            results.map((item, idx) => (
              <li key={item.id} role="option" aria-selected={idx === active}>
                <button
                  type="button"
                  className={cn(
                    "flex w-full items-center justify-between gap-2 p-2.5 text-left text-sm hover:bg-accent",
                    idx === active && "bg-accent",
                  )}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => select(item.id)}
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium">
                      {item.name ?? item.external_id}
                    </span>
                    <span className="block text-[10px] text-muted-foreground">
                      {item.resource_type} · {item.integration_id}
                    </span>
                  </span>
                  <StatusBadge status={item.status} />
                </button>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
