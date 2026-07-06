import * as React from "react";
import { toast } from "sonner";
import { Users, Route, Loader2 } from "lucide-react";

import { endpoints, type NetworkBlock } from "@/api/client";
import { friendlyError } from "@/lib/friendly-error";
import { PromptDialog } from "@/components/prompt-dialog";
import { Button } from "@/components/ui/button";

/* "Your network" — the referral surface shown in the Inbox detail pane and the
 * JobDialog (B4). When the user has imported LinkedIn/Google contacts that work at
 * this job's company, it lists a few of them and offers a "Find my path in
 * {company}" button that builds a BYO-AI warm-path prompt (ranked paths, LinkedIn
 * search strings the user runs themselves, two outreach drafts). Prompt-only — the
 * copy goes into whatever AI the user already uses. Renders nothing extra when
 * there are no matches, but STILL offers the warm-path button (indirect paths —
 * alumni/past-colleague — don't require a direct contact).
 *
 * `source` decides which endpoint builds the prompt (inbox row vs tracked
 * application); both return {ok, prompt} with identical shape. */

export interface NetworkBlockViewProps {
  company: string;
  network: NetworkBlock | undefined;
  id: number;
  source: "inbox" | "application";
}

export function NetworkBlockView({
  company,
  network,
  id,
  source,
}: NetworkBlockViewProps) {
  const [prompt, setPrompt] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const [building, setBuilding] = React.useState(false);

  const count = network?.count ?? 0;
  const contacts = network?.contacts ?? [];
  const companyLabel = company || "this company";

  const findPath = React.useCallback(() => {
    setBuilding(true);
    const call =
      source === "inbox"
        ? endpoints.inboxWarmPathPrompt(id)
        : endpoints.appWarmPathPrompt(id);
    call
      .then((r) => {
        setPrompt(r.prompt);
        setOpen(true);
      })
      .catch((e) =>
        toast.error("Couldn't build the warm-path prompt", {
          description: friendlyError(e),
        }),
      )
      .finally(() => setBuilding(false));
  }, [id, source]);

  return (
    <section className="space-y-2">
      <h3 className="text-muted-foreground flex items-center gap-1.5 text-xs font-semibold tracking-wide uppercase">
        <Users className="size-3.5" />
        Your network
      </h3>

      {count > 0 ? (
        <div className="space-y-2">
          <p className="text-foreground/90 text-sm leading-relaxed">
            <span className="zg-num font-semibold">{count}</span>{" "}
            {count === 1 ? "person" : "people"} in your network{" "}
            {count === 1 ? "works" : "work"} at{" "}
            <span className="font-medium">{companyLabel}</span>.
          </p>
          <ul className="space-y-1">
            {contacts.map((c, i) => (
              <li
                key={`${c.name}-${i}`}
                className="text-muted-foreground text-sm"
              >
                <span className="text-foreground">{c.name}</span>
                {c.position ? ` · ${c.position}` : ""}
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground text-xs">
            A referral is the highest-conversion way in — reach out before you
            apply.
          </p>
        </div>
      ) : (
        <p className="text-muted-foreground text-sm leading-relaxed">
          No one from your imported contacts works here yet. You may still have
          an alumni or past-colleague path in — let your AI find it.
        </p>
      )}

      <Button
        size="sm"
        variant="outline"
        onClick={findPath}
        disabled={building}
        className="mt-1"
      >
        {building ? (
          <Loader2 className="size-3.5 animate-spin" />
        ) : (
          <Route className="size-3.5" />
        )}
        Find my path in {companyLabel}
      </Button>

      <PromptDialog
        open={open}
        onOpenChange={setOpen}
        title={`Warm path into ${companyLabel}`}
        description="Copy this into your AI. It returns ranked warm paths, LinkedIn searches you run yourself, and two outreach drafts in your voice."
        prompt={prompt}
      />
    </section>
  );
}
