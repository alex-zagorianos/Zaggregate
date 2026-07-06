import * as React from "react";
import { BookOpen } from "lucide-react";

import { useGuide } from "@/api/queries";
import type { GuideSection } from "@/api/client";
import { EmptyState, useQueryGuard } from "@/components/states";

/* Guide — the in-app help, rendered as an editorial reading page. This is the
 * typography showcase for the whole app: Fraunces headings at a real display
 * size, a comfortable ~66-character measure, generous leading, drop-cap-free but
 * print-quality rhythm. Content is the Tk-free help_core.GUIDE, structured into
 * {heading, level, body} sections by the server.
 *
 * A sticky section index (on wide viewports) lets the reader jump around; each
 * section anchors by a slug of its heading. Body text is the raw guide prose —
 * we render paragraphs (blank-line-separated) and simple bullet lines, no full
 * markdown engine (the guide content is plain prose + dashes). */

export function GuideTab() {
  const query = useGuide();
  const sections = query.data?.sections ?? [];

  const guard = useQueryGuard(query, {
    title: "Couldn't load the guide",
    fallback: "The guide service didn't respond.",
  });
  if (guard) return guard;
  if (sections.length === 0) {
    return (
      <EmptyState
        icon={BookOpen}
        title="The guide is empty"
        message="No guide content is available."
      />
    );
  }

  const majors = sections.filter((s) => s.level <= 1);

  return (
    <div className="mx-auto grid max-w-5xl grid-cols-1 gap-10 lg:grid-cols-[1fr_15rem]">
      {/* The reading column */}
      <article className="min-w-0">
        <header className="mb-10">
          <p className="text-primary mb-2 flex items-center gap-2 text-sm font-medium tracking-wide uppercase">
            <BookOpen className="size-4" />
            Guide
          </p>
          <h1 className="zg-serif text-foreground text-4xl leading-[1.1] font-semibold tracking-tight sm:text-5xl">
            How Zaggregate works
          </h1>
          <p className="text-muted-foreground mt-4 max-w-[42ch] text-lg leading-relaxed">
            Everything you need to find, rank, and apply — from your first daily
            run to a tracked offer.
          </p>
        </header>

        <div className="space-y-12">
          {sections.map((s, i) => (
            <GuideSectionBlock key={`${slugify(s.heading)}-${i}`} section={s} />
          ))}
        </div>
      </article>

      {/* Sticky section index — desktop only */}
      <nav aria-label="Guide sections" className="hidden lg:block">
        <div className="sticky top-32 space-y-1">
          <p className="text-muted-foreground mb-3 text-xs font-semibold tracking-wide uppercase">
            On this page
          </p>
          <ul className="space-y-0.5 border-l border-border">
            {majors.map((s, i) => (
              <li key={`toc-${slugify(s.heading)}-${i}`}>
                <a
                  href={`#${slugify(s.heading)}`}
                  className="text-muted-foreground hover:text-foreground hover:border-primary -ml-px block border-l-2 border-transparent py-1 pl-3 text-sm leading-snug transition-colors"
                >
                  {s.heading}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </nav>
    </div>
  );
}

function GuideSectionBlock({ section }: { section: GuideSection }) {
  const id = slugify(section.heading);
  const isMajor = section.level <= 1;
  return (
    <section id={id} className="scroll-mt-32">
      {isMajor ? (
        <h2 className="zg-serif text-foreground border-border mb-4 border-b pb-2 text-2xl font-semibold tracking-tight sm:text-3xl">
          {section.heading}
        </h2>
      ) : (
        <h3 className="zg-serif text-foreground mb-3 text-xl font-semibold tracking-tight">
          {section.heading}
        </h3>
      )}
      <GuideBody body={section.body} />
    </section>
  );
}

/** Render the plain guide prose: split on blank lines into blocks; a block whose
 * lines all start with a bullet marker becomes a <ul>, otherwise a <p>. No
 * markdown engine — the guide is plain prose + dash bullets. */
function GuideBody({ body }: { body: string }) {
  const blocks = React.useMemo(() => splitBlocks(body), [body]);
  if (blocks.length === 0) return null;
  return (
    <div className="space-y-4">
      {blocks.map((block, i) =>
        block.kind === "list" ? (
          <ul
            key={i}
            className="text-foreground/90 marker:text-primary/60 max-w-[66ch] list-disc space-y-1.5 pl-5 text-[0.975rem] leading-relaxed"
          >
            {block.items.map((it, j) => (
              <li key={j}>{it}</li>
            ))}
          </ul>
        ) : (
          <p
            key={i}
            className="text-foreground/90 max-w-[66ch] text-[0.975rem] leading-[1.75]"
          >
            {block.text}
          </p>
        ),
      )}
    </div>
  );
}

type Block = { kind: "para"; text: string } | { kind: "list"; items: string[] };

const BULLET_RE = /^\s*[-*•]\s+/;

function splitBlocks(body: string): Block[] {
  const paras = (body || "").split(/\n\s*\n/);
  const out: Block[] = [];
  for (const para of paras) {
    const lines = para.split("\n").map((l) => l.trimEnd());
    const nonEmpty = lines.filter((l) => l.trim());
    if (nonEmpty.length === 0) continue;
    const bulletCount = nonEmpty.filter((l) => BULLET_RE.test(l)).length;
    if (bulletCount >= Math.ceil(nonEmpty.length / 2) && bulletCount > 0) {
      out.push({
        kind: "list",
        items: nonEmpty.map((l) => l.replace(BULLET_RE, "").trim()),
      });
    } else {
      out.push({ kind: "para", text: nonEmpty.join(" ") });
    }
  }
  return out;
}

/** A URL-safe anchor slug from a heading. */
function slugify(heading: string): string {
  return (
    (heading || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 60) || "section"
  );
}
