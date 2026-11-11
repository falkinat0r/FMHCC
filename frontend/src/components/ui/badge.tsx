import type { HTMLAttributes } from "react";

import { cn } from "../../lib/cn";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "secondary" | "outline" | "destructive" | "status";
}

/** shadcn-artiges Badge. */
export function Badge({
  className,
  variant = "default",
  ...props
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-none",
        variant === "default" && "border-transparent bg-primary text-primary-foreground",
        variant === "secondary" && "border-transparent bg-secondary text-secondary-foreground",
        variant === "outline" && "border-border text-muted-foreground",
        variant === "destructive" && "border-transparent bg-destructive/15 text-destructive",
        variant === "status" && "border-transparent",
        className,
      )}
      {...props}
    />
  );
}
