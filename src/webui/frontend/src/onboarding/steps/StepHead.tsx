import type { ReactNode } from "react";

/* The shared wizard step header: an accent eyebrow (icon + kicker), a serif
 * title, and a sub-line at the editorial measure. One place so every step reads
 * with the same hierarchy + rhythm. */
export function StepHead({
  icon,
  eyebrow,
  title,
  sub,
}: {
  icon: ReactNode;
  eyebrow: string;
  title: string;
  sub: string;
}) {
  return (
    <div>
      <p className="text-primary mb-3 flex items-center gap-2 text-sm font-medium tracking-wide uppercase">
        {icon}
        {eyebrow}
      </p>
      <h2 className="zg-serif text-foreground text-3xl leading-tight font-semibold tracking-tight sm:text-4xl">
        {title}
      </h2>
      <p className="text-muted-foreground mt-3 max-w-[48ch] text-lg leading-relaxed">
        {sub}
      </p>
    </div>
  );
}
