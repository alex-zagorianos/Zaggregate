import * as React from "react";

import { cn } from "@/lib/utils";

/* shadcn/ui Table (new-york), Aegean-tuned: square corners (the identity's
 * "square table corners"), hairline row separators, a faint header rule, and a
 * subtle hover tint. The outer scroll container keeps wide tables from pushing
 * the page body sideways (global constraint: the body never scrolls X). */
function Table({ className, ...props }: React.ComponentProps<"table">) {
  return (
    <div
      data-slot="table-container"
      className="relative w-full overflow-x-auto"
    >
      <table
        data-slot="table"
        className={cn("w-full caption-bottom text-sm", className)}
        {...props}
      />
    </div>
  );
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead
      data-slot="table-header"
      className={cn("[&_tr]:border-b", className)}
      {...props}
    />
  );
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("[&_tr:last-child]:border-0", className)}
      {...props}
    />
  );
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        "border-border/70 hover:bg-secondary/45 data-[state=selected]:bg-secondary/60 border-b transition-colors outline-none",
        "focus-visible:bg-secondary/50 focus-visible:ring-ring/40 focus-visible:ring-2 focus-visible:ring-inset",
        className,
      )}
      {...props}
    />
  );
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "text-muted-foreground h-10 px-3 text-left align-middle text-xs font-semibold tracking-wide uppercase whitespace-nowrap",
        "[&:has([role=checkbox])]:pr-0",
        className,
      )}
      {...props}
    />
  );
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        "px-3 py-2.5 align-middle [&:has([role=checkbox])]:pr-0",
        className,
      )}
      {...props}
    />
  );
}

export { Table, TableHeader, TableBody, TableRow, TableHead, TableCell };
