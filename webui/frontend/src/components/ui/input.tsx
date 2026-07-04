import * as React from "react";

import { cn } from "@/lib/utils";

/* shadcn/ui Input (new-york), Aegean-tuned. Hairline border, 7px radius, accent
 * focus ring (keyboard + programmatic focus both land the ring). Height matches
 * the sm Button so field + button rows align. */
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "border-input bg-background placeholder:text-muted-foreground/70 flex h-9 w-full min-w-0 rounded-md border px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none",
        "file:text-foreground file:inline-flex file:border-0 file:bg-transparent file:text-sm file:font-medium",
        "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
        "aria-invalid:border-destructive aria-invalid:ring-destructive/30",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
