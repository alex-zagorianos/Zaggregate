import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** shadcn's class-name merge helper: conditional classes (clsx) + Tailwind
 * conflict resolution (tailwind-merge). Used by every shadcn/ui primitive. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
