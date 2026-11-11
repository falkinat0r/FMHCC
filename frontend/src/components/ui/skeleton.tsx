import type { HTMLAttributes } from "react";

import { cn } from "../../lib/cn";

/** Lade-Platzhalter (keine Animation ueber Mass, nur dezent). */
export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  );
}
