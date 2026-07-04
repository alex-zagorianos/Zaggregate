import * as React from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

/* A lightweight styled <select>. We use the NATIVE select (not
 * @radix-ui/react-select) deliberately: it's one control, needs no extra dep,
 * and the native popup is keyboard- and screen-reader-correct for free. The
 * wrapper draws the Aegean field chrome + a chevron; the real <select> sits on
 * top, transparent, so clicks/keys hit it directly. */
function Select({
  className,
  children,
  ...props
}: React.ComponentProps<"select">) {
  return (
    <div className="relative inline-flex">
      <select
        data-slot="select"
        className={cn(
          "border-input bg-background text-foreground h-9 w-full appearance-none rounded-md border py-1 pr-8 pl-3 text-sm shadow-xs transition-[color,box-shadow] outline-none",
          "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown className="text-muted-foreground pointer-events-none absolute top-1/2 right-2.5 size-4 -translate-y-1/2 opacity-70" />
    </div>
  );
}

export { Select };
