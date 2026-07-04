import * as React from "react";

import { cn } from "@/lib/utils";

/* Minimal label primitive (no @radix-ui/react-label dep — a plain styled
 * <label> is enough for our forms and keeps the bundle lean). */
function Label({ className, ...props }: React.ComponentProps<"label">) {
  return (
    <label
      data-slot="label"
      className={cn(
        "text-foreground flex items-center gap-2 text-sm leading-none font-medium select-none",
        "peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export { Label };
