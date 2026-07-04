import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

/* Small status/label chip. `status` colors come from the generated
 * --zg-status-* tokens (Job-Tracker statuses) applied inline by the caller; the
 * variants here cover the generic cases. Square-ish corners (radius-chip). */
const badgeVariants = cva(
  "inline-flex items-center justify-center gap-1 rounded-[var(--radius-chip)] border px-2 py-0.5 text-xs font-medium w-fit whitespace-nowrap shrink-0 transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "border-border text-foreground",
        accent: "border-transparent bg-accent text-accent-foreground",
        success:
          "border-transparent bg-[var(--zg-success)]/15 text-[var(--zg-success)]",
        warn: "border-transparent bg-[var(--zg-warn)]/15 text-[var(--zg-warn)]",
        danger: "border-transparent bg-destructive/12 text-destructive",
      },
    },
    defaultVariants: {
      variant: "secondary",
    },
  },
);

function Badge({
  className,
  variant,
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "span";
  return (
    <Comp
      data-slot="badge"
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  );
}

export { Badge, badgeVariants };
