import { Inbox, Star, Sparkles, ListChecks } from "lucide-react";

/* Step 1 — Welcome. Sets the tone: a serif hero, a one-line promise, and three
 * "what you'll get" cards. No input; always valid. This is the very first thing a
 * new user sees, so it leans on the editorial voice + generous whitespace. */

export function WelcomeStep() {
  return (
    <div className="max-w-2xl">
      <p className="text-primary mb-3 flex items-center gap-2 text-sm font-medium tracking-wide uppercase">
        <Sparkles className="size-4" />
        Welcome
      </p>
      <h1 className="zg-serif text-foreground text-4xl leading-[1.08] font-semibold tracking-tight sm:text-5xl">
        Let's find work
        <br />
        worth showing up for.
      </h1>
      <p className="text-muted-foreground mt-5 max-w-[46ch] text-lg leading-relaxed">
        A couple of quick questions and Zaggregate starts pulling jobs from
        every board at once, ranking each for how well it fits you. This takes
        about a minute — or hand it to your AI and skip straight to the good
        part.
      </p>

      <div className="mt-9 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <PromiseCard
          icon={<Inbox className="size-5" />}
          title="One inbox"
          body="Every board, deduplicated and scored, in a single place to triage."
        />
        <PromiseCard
          icon={<Star className="size-5" />}
          title="Ranked for you"
          body="The best matches float up. Your AI can re-rank on your own taste."
        />
        <PromiseCard
          icon={<ListChecks className="size-5" />}
          title="Tracked to offer"
          body="Move jobs across a board from applied to interview to offer."
        />
      </div>
    </div>
  );
}

function PromiseCard({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="border-border bg-card/60 rounded-lg border p-4">
      <div className="text-primary mb-2.5">{icon}</div>
      <h3 className="zg-serif text-foreground text-base font-semibold tracking-tight">
        {title}
      </h3>
      <p className="text-muted-foreground mt-1 text-sm leading-relaxed">
        {body}
      </p>
    </div>
  );
}
