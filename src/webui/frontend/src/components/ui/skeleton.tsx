import { cn } from "@/lib/utils";

/** A loading placeholder block. Uses the secondary fill so it reads as "content
 * loading" in both themes without a garish shimmer. */
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("bg-secondary/70 animate-pulse rounded-md", className)}
      {...props}
    />
  );
}

export { Skeleton };
