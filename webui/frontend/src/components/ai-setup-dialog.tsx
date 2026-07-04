import * as React from "react";
import { toast } from "sonner";
import {
  Copy,
  Check,
  Loader2,
  Sparkles,
  CheckCircle2,
  ArrowRight,
} from "lucide-react";

import { endpoints, ApiError, type AiSetupApplied } from "@/api/client";
import { useApplyAiSetup } from "@/api/queries";
import { copyText } from "@/lib/clipboard";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { formatDollars } from "@/lib/salary-hint";

/* AI express-lane — the "let my AI set me up" flow. A single dialog with three
 * panes:
 *   1. copy    — the copyable setup prompt (GET /api/ai-setup/prompt). The user
 *                pastes it into claude.ai above their résumé + one line of intent.
 *   2. paste   — a textarea for the AI's returned config block.
 *   3. applied — the summary the server echoes after a successful apply
 *                (field, titles, location, salary, seniority).
 *
 * On apply success it fires `onApplied` so the wizard can jump to Finish / the
 * app can close the welcome takeover. A bad block surfaces the server's
 * human-actionable 400 message inline (no partial apply). Reuses the shared
 * clipboard helper + Aegean primitives. */

export interface AiSetupDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Fires after a successful apply (the config landed on disk). */
  onApplied?: (applied: AiSetupApplied) => void;
}

type Pane = "copy" | "paste" | "applied";

export function AiSetupDialog({
  open,
  onOpenChange,
  onApplied,
}: AiSetupDialogProps) {
  const [pane, setPane] = React.useState<Pane>("copy");
  const [prompt, setPrompt] = React.useState("");
  const [promptLoading, setPromptLoading] = React.useState(false);
  const [copied, setCopied] = React.useState(false);
  const [reply, setReply] = React.useState("");
  const [applied, setApplied] = React.useState<AiSetupApplied | null>(null);
  const applyMut = useApplyAiSetup();

  // Fresh state each open; fetch the prompt lazily on first open.
  React.useEffect(() => {
    if (!open) return;
    setPane("copy");
    setReply("");
    setCopied(false);
    setApplied(null);
    if (!prompt) {
      setPromptLoading(true);
      endpoints
        .aiSetupPrompt()
        .then((r) => setPrompt(r.prompt))
        .catch((e) =>
          toast.error("Couldn't load the setup prompt", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          }),
        )
        .finally(() => setPromptLoading(false));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const onCopy = async () => {
    const ok = await copyText(prompt);
    if (ok) {
      setCopied(true);
      toast.success("Prompt copied", {
        description:
          "Paste it into your AI above your résumé, then paste the reply back.",
      });
      window.setTimeout(() => setCopied(false), 1600);
    } else {
      toast.error("Couldn't copy", {
        description: "Select the text and copy it manually.",
      });
    }
  };

  const onApply = () => {
    const text = reply.trim();
    if (!text) return;
    applyMut.mutate(text, {
      onSuccess: (res) => {
        setApplied(res.applied);
        setPane("applied");
        onApplied?.(res.applied);
      },
      onError: (e) =>
        toast.error("Couldn't apply that reply", {
          description:
            e instanceof ApiError
              ? e.message
              : "The reply wasn't in the expected format.",
        }),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="zg-serif flex items-center gap-2">
            <Sparkles className="text-primary size-5" />
            Set up with your AI
          </DialogTitle>
          <DialogDescription>
            {pane === "applied"
              ? "Your preferences are in — here's what we set."
              : "Copy the prompt into claude.ai (or any chatbot) above your résumé and one sentence about what you want. Paste its reply back here."}
          </DialogDescription>
        </DialogHeader>

        {pane === "copy" && (
          <>
            <div className="border-primary/25 bg-accent/40 flex items-start gap-2.5 rounded-md border p-3 text-sm">
              <span className="bg-primary text-primary-foreground zg-num mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-xs font-semibold">
                1
              </span>
              <p className="text-foreground/90 leading-relaxed">
                Copy this prompt, paste it into your AI, then add your résumé
                and a sentence like{" "}
                <em>"I want mechanical design roles near Cincinnati."</em>
              </p>
            </div>
            <Textarea
              value={promptLoading ? "Loading…" : prompt}
              readOnly
              rows={9}
              className="text-xs"
              onFocus={(e) => e.currentTarget.select()}
            />
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={onCopy}
                disabled={promptLoading}
              >
                {copied ? (
                  <Check className="size-4" />
                ) : (
                  <Copy className="size-4" />
                )}
                {copied ? "Copied" : "Copy prompt"}
              </Button>
              <Button
                size="sm"
                onClick={() => setPane("paste")}
                disabled={promptLoading}
              >
                I've got the reply
                <ArrowRight className="size-4" />
              </Button>
            </div>
          </>
        )}

        {pane === "paste" && (
          <>
            <div className="border-primary/25 bg-accent/40 flex items-start gap-2.5 rounded-md border p-3 text-sm">
              <span className="bg-primary text-primary-foreground zg-num mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-xs font-semibold">
                2
              </span>
              <p className="text-foreground/90 leading-relaxed">
                Paste the AI's reply below. We only read the config block it
                produced — nothing is sent anywhere.
              </p>
            </div>
            <Textarea
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              placeholder="Paste the AI's reply here…"
              rows={9}
              className="text-sm"
              autoFocus
            />
            <div className="flex justify-between gap-2">
              <Button variant="ghost" size="sm" onClick={() => setPane("copy")}>
                Back
              </Button>
              <Button
                size="sm"
                onClick={onApply}
                disabled={applyMut.isPending || !reply.trim()}
              >
                {applyMut.isPending && (
                  <Loader2 className="size-3.5 animate-spin" />
                )}
                Apply setup
              </Button>
            </div>
          </>
        )}

        {pane === "applied" && applied && (
          <AppliedSummary
            applied={applied}
            onDone={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function AppliedSummary({
  applied,
  onDone,
}: {
  applied: AiSetupApplied;
  onDone: () => void;
}) {
  const rows: { label: string; value: React.ReactNode }[] = [
    { label: "Field", value: applied.field || "—" },
    {
      label: "Target roles",
      value:
        applied.target_titles.length > 0 ? (
          <span className="flex flex-wrap gap-1">
            {applied.target_titles.slice(0, 6).map((t) => (
              <Badge key={t} variant="secondary">
                {t}
              </Badge>
            ))}
          </span>
        ) : (
          "—"
        ),
    },
    { label: "Location", value: applied.location || "—" },
    {
      label: "Remote",
      value: applied.remote_only ? "Remote only" : "Remote OK",
    },
    {
      label: "Salary floor",
      value:
        applied.salary_min && applied.salary_min > 0
          ? `${formatDollars(applied.salary_min)} / yr`
          : "—",
    },
    { label: "Seniority", value: applied.seniority || "—" },
  ];
  return (
    <>
      <div className="border-[var(--zg-success)]/30 bg-[var(--zg-success)]/8 flex items-center gap-2.5 rounded-md border p-3">
        <CheckCircle2 className="size-5 shrink-0 text-[var(--zg-success)]" />
        <p className="text-foreground text-sm">
          Preferences saved from your AI's reply
          {applied.profile_chars > 0 && (
            <span className="text-muted-foreground">
              {" "}
              · {applied.profile_chars.toLocaleString()} characters of profile
            </span>
          )}
          .
        </p>
      </div>
      <dl className="divide-border divide-y text-sm">
        {rows.map((r) => (
          <div
            key={r.label}
            className="flex items-start justify-between gap-4 py-2"
          >
            <dt className="text-muted-foreground shrink-0">{r.label}</dt>
            <dd className="text-foreground text-right">{r.value}</dd>
          </div>
        ))}
      </dl>
      <div className="flex justify-end">
        <Button size="sm" onClick={onDone}>
          Done
        </Button>
      </div>
    </>
  );
}
