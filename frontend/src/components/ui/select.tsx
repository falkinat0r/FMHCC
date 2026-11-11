import { forwardRef, type SelectHTMLAttributes } from "react";

import { cn } from "../../lib/cn";

/**
 * shadcn-artiges Select (stilisiertes natives <select>).
 * Natives Element = volle Keyboard-/Screenreader-Suette ohne
 * Radix-Abhaengigkeit.
 */
export const Select = forwardRef<
  HTMLSelectElement,
  SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      "flex h-9 w-full appearance-none rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm",
      "focus-visible:outline-2 focus-visible:outline-ring",
      "disabled:cursor-not-allowed disabled:opacity-50",
      "bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20width%3D%2212%22%20height%3D%2212%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%2393a1b0%22%20stroke-width%3D%222%22%3E%3Cpath%20d%3D%22m6%209%206%206%206-6%22/%3E%3C/svg%3E')] bg-no-repeat bg-[right_0.6rem_center] pr-8",
      className,
    )}
    {...props}
  >
    {children}
  </select>
));
Select.displayName = "Select";
