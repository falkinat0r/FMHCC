import { Fragment, type ReactNode } from "react";

import { cn } from "../../lib/cn";

export interface TabDef {
  readonly value: string;
  readonly label: string;
  readonly icon?: ReactNode;
}

interface TabsProps {
  tabs: readonly TabDef[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
}

/**
 * Zugaeafige Tabs (role=tablist/tab, arrow-key Navigation).
 * Der Inhalt wird vom aufrufenden Feature gerendert.
 */
export function Tabs({ tabs, value, onChange, className }: TabsProps) {
  return (
    <div
      role="tablist"
      aria-orientation="horizontal"
      className={cn(
        "inline-flex items-center gap-1 rounded-lg border border-border bg-muted/40 p-1",
        className,
      )}
      onKeyDown={(event) => {
        const idx = tabs.findIndex((t) => t.value === value);
        if (idx < 0) return;
        let next = idx;
        if (event.key === "ArrowRight") next = (idx + 1) % tabs.length;
        else if (event.key === "ArrowLeft")
          next = (idx - 1 + tabs.length) % tabs.length;
        else return;
        event.preventDefault();
        const target = tabs[next];
        if (target) {
          onChange(target.value);
          requestAnimationFrame(() => {
            document
              .querySelector<HTMLButtonElement>(
                `#tab-${CSS.escape(target.value)}`,
              )
              ?.focus();
          });
        }
      }}
    >
      {tabs.map((tab) => (
        <Fragment key={tab.value}>
          <button
            id={`tab-${tab.value}`}
            role="tab"
            aria-selected={tab.value === value}
            onClick={() => onChange(tab.value)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
              tab.value === value
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.icon}
            {tab.label}
          </button>
        </Fragment>
      ))}
    </div>
  );
}
