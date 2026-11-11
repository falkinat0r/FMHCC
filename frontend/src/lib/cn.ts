import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Verbindet Tailwind-Klassen, spaltet Konstellationen (shadcn-Konvention). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
