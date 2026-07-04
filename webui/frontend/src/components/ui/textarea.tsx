import * as React from "react";

import { cn } from "@/lib/utils";

/* shadcn/ui Textarea (new-york), Aegean-tuned to match Input's chrome — hairline
 * border, 7px radius, accent focus ring. Used by the JobDialog notes + round-notes
 * fields. Vertical resize only so it can't break the sheet's horizontal rhythm. */
function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "border-input bg-background placeholder:text-muted-foreground/70 flex min-h-[4.5rem] w-full resize-y rounded-md border px-3 py-2 text-sm shadow-xs transition-[color,box-shadow] outline-none",
        "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
        "aria-invalid:border-destructive aria-invalid:ring-destructive/30",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
