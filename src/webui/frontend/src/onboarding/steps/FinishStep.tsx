import * as React from "react";
import { PartyPopper, CalendarClock, ListPlus, Loader2 } from "lucide-react";

import {
  parseRoles,
  resolveIndustry,
  type WizardAnswers,
} from "@/lib/wizard-steps";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { StepHead } from "./StepHead";

/* Step 7 — Finish. A recap of the essentials, a note about the daily update, a
 * Build-My-List opt-in, and the primary "Take me to my inbox" button that POSTs
 * the answers (owned by the parent's onFinish). The opt-in is passed up so the
 * wizard can kick off a background list build. */

export function FinishStep({
  answers,
  onFinish,
  finishing,
}: {
  answers: WizardAnswers;
  onFinish: (buildListOptIn: boolean) => void;
  finishing: boolean;
}) {
  const [buildList, setBuildList] = React.useState(false);
  const roles = parseRoles(answers.roles);
  const field = resolveIndustry(answers);

  return (
    <div className="max-w-2xl">
      <StepHead
        icon={<PartyPopper className="size-4" />}
        eyebrow="All set"
        title="You're ready to go."
        sub="Here's what we'll look for. You can change any of it later from Search and the gear menu."
      />

      <dl className="border-border mt-8 divide-y divide-border rounded-lg border">
        <Recap label="Roles">
          {roles.length > 0 ? (
            <span className="flex flex-wrap justify-end gap-1">
              {roles.slice(0, 6).map((r) => (
                <Badge key={r} variant="secondary">
                  {r}
                </Badge>
              ))}
            </span>
          ) : (
            "—"
          )}
        </Recap>
        {field && <Recap label="Field">{field}</Recap>}
        <Recap label="Where">
          {answers.location || "Anywhere"}
          {answers.remoteOk && (
            <span className="text-muted-foreground"> · remote OK</span>
          )}
        </Recap>
        {answers.salaryText.trim() && (
          <Recap label="Min salary">
            <span className="zg-num">{answers.salaryText.trim()}</span>
          </Recap>
        )}
        {answers.level && <Recap label="Level">{answers.level}</Recap>}
      </dl>

      <div className="border-border bg-card/60 mt-6 flex items-start gap-3 rounded-lg border p-4">
        <CalendarClock className="text-primary mt-0.5 size-5 shrink-0" />
        <p className="text-foreground/90 text-sm leading-relaxed">
          Zaggregate refreshes your inbox with a{" "}
          <strong className="text-foreground">daily update</strong> — new,
          scored jobs waiting each time you open it. Run it any time from the
          Inbox.
        </p>
      </div>

      <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-lg p-1 text-sm">
        <input
          type="checkbox"
          checked={buildList}
          onChange={(e) => setBuildList(e.target.checked)}
          className="accent-[var(--zg-accent)] mt-0.5 size-4"
        />
        <span>
          <span className="text-foreground flex items-center gap-1.5 font-medium">
            <ListPlus className="size-4 opacity-70" />
            Build my company list now
          </span>
          <span className="text-muted-foreground">
            Kick off a background scan for employers in your field and area. You
            can also do this later from the palette.
          </span>
        </span>
      </label>

      <div className="mt-8 flex justify-end">
        <Button
          size="lg"
          onClick={() => onFinish(buildList)}
          disabled={finishing}
        >
          {finishing ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <PartyPopper className="size-4" />
          )}
          Take me to my inbox
        </Button>
      </div>
    </div>
  );
}

function Recap({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 px-4 py-3 text-sm">
      <dt className="text-muted-foreground shrink-0">{label}</dt>
      <dd className="text-foreground text-right">{children}</dd>
    </div>
  );
}
