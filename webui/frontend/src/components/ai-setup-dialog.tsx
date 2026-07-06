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

import {
  endpoints,
  ApiError,
  type AiSetupApplyResponse,
  type ApplyAiSetupFullResponse,
} from "@/api/client";
import { useApplyAiSetup, useApplyAiSetupFull } from "@/api/queries";
import {
  configResult,
  fullResult,
  showsSeedRow,
  type AiSetupPromptKind,
  type AiSetupResult,
} from "@/lib/ai-setup-logic";
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

/* AI express-lane — the "let my AI set me up" flow.
 *
 * The reusable core is `AiSetupPanes`: a three-pane state machine (copy → paste →
 * applied) with NO dialog chrome, so it can be embedded INLINE (the wizard's AI-
 * first landing) OR wrapped in a `Dialog` (`AiSetupDialog`, the Search-tab entry).
 *   1. copy    — the copyable setup prompt. `promptKind` picks which:
 *                "config" = GET /api/ai-setup/prompt (config-only, the classic
 *                express lane); "full" = the combined config+seeds prompt (S40,
 *                backend `?full=1`) whose one reply also seeds companies + can
 *                start the first search.
 *   2. paste   — a textarea for the AI's returned block.
 *   3. applied — the summary the server echoes after a successful apply.
 *
 * On apply success it fires `onApplied(res)` so the caller can react — the wizard
 * navigates to the Inbox with the run console attached (res.job_id from apply-full);
 * the Search-tab dialog shows a "Run search now" button. `autorun` (only meaningful
 * for promptKind "full") decides whether apply-full also STARTS the first-run job:
 * the wizard passes true (one paste = searching); the Search-tab dialog passes false
 * (config lands, the user runs when ready). A bad block surfaces the server's
 * human-actionable 400 message inline (no partial apply). Reuses the shared clipboard
 * helper + Aegean primitives. */

// The pane types + result-shape helpers live in lib/ai-setup-logic (pure, node-
// testable). Re-exported here so existing importers keep their import path.
export type { AiSetupPromptKind, AiSetupResult } from "@/lib/ai-setup-logic";

export interface AiSetupPanesProps {
  /** Which prompt to copy + which apply route to call. */
  promptKind: AiSetupPromptKind;
  /** For "full": also start the first-run job on apply (ignored for "config"). */
  autorun: boolean;
  /** Fires after a successful apply (the config landed on disk). */
  onApplied?: (res: AiSetupResult) => void;
  /** Optional extra content rendered in the applied pane, LEFT of the Done button
   * (e.g. the Search-tab dialog's "Run search now"). Receives the apply result so
   * it can, e.g., fire a run. */
  appliedExtra?: (res: AiSetupResult) => React.ReactNode;
  /** Called when the applied pane's Done button is clicked (dialog: close). Inline
   * embeds (the wizard) usually navigate away in onApplied and never show Done. */
  onDone?: () => void;
}

type Pane = "copy" | "paste" | "applied";

export function AiSetupPanes({
  promptKind,
  autorun,
  onApplied,
  appliedExtra,
  onDone,
}: AiSetupPanesProps) {
  const [pane, setPane] = React.useState<Pane>("copy");
  const [prompt, setPrompt] = React.useState("");
  const [promptLoading, setPromptLoading] = React.useState(false);
  const [copied, setCopied] = React.useState(false);
  const [reply, setReply] = React.useState("");
  const [result, setResult] = React.useState<AiSetupResult | null>(null);
  const applyConfigMut = useApplyAiSetup();
  const applyFullMut = useApplyAiSetupFull();
  const applying = applyConfigMut.isPending || applyFullMut.isPending;

  // Fetch the right prompt lazily on first mount. The two kinds fetch different
  // endpoints (config vs `?full=1`), so re-fetch if promptKind changes.
  React.useEffect(() => {
    setPromptLoading(true);
    const fetcher =
      promptKind === "full"
        ? endpoints.aiSetupFullPrompt()
        : endpoints.aiSetupPrompt();
    fetcher
      .then((r) => setPrompt(r.prompt))
      .catch((e) =>
        toast.error("Couldn't load the setup prompt", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
      )
      .finally(() => setPromptLoading(false));
  }, [promptKind]);

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
    const settle = (res: AiSetupResult) => {
      setResult(res);
      setPane("applied");
      onApplied?.(res);
    };
    const onError = (e: unknown) =>
      toast.error("Couldn't apply that reply", {
        description:
          e instanceof ApiError
            ? e.message
            : "The reply wasn't in the expected format.",
      });

    if (promptKind === "full") {
      applyFullMut.mutate(
        { text, autorun },
        {
          onSuccess: (res: ApplyAiSetupFullResponse) => settle(fullResult(res)),
          onError,
        },
      );
    } else {
      applyConfigMut.mutate(text, {
        onSuccess: (res: AiSetupApplyResponse) => settle(configResult(res)),
        onError,
      });
    }
  };

  return (
    <>
      {pane === "copy" && (
        <>
          <div className="border-primary/25 bg-accent/40 flex items-start gap-2.5 rounded-md border p-3 text-sm">
            <span className="bg-primary text-primary-foreground zg-num mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-xs font-semibold">
              1
            </span>
            <p className="text-foreground/90 leading-relaxed">
              Copy this prompt, paste it into your AI, then add your résumé and
              a sentence like{" "}
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
              disabled={applying || !reply.trim()}
            >
              {applying && <Loader2 className="size-3.5 animate-spin" />}
              Apply setup
            </Button>
          </div>
        </>
      )}

      {pane === "applied" && result && (
        <AppliedSummary
          result={result}
          onDone={onDone}
          extra={appliedExtra ? appliedExtra(result) : undefined}
        />
      )}
    </>
  );
}

/* ── the dialog wrapper ─────────────────────────────────────────────────────────
 * A thin Dialog around `AiSetupPanes`. Fresh pane state each open is achieved by
 * keying the panes on `open` (remount on every open), matching the old behavior. */

export interface AiSetupDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Which prompt/apply contract to drive (default "config" = the classic lane). */
  promptKind?: AiSetupPromptKind;
  /** For "full": also start the first-run job on apply (default false in the
   * dialog — the Search-tab entry runs on demand via the applied-pane button). */
  autorun?: boolean;
  /** Fires after a successful apply. */
  onApplied?: (res: AiSetupResult) => void;
  /** Optional extra applied-pane content (e.g. "Run search now"). */
  appliedExtra?: (res: AiSetupResult) => React.ReactNode;
}

export function AiSetupDialog({
  open,
  onOpenChange,
  promptKind = "config",
  autorun = false,
  onApplied,
  appliedExtra,
}: AiSetupDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="zg-serif flex items-center gap-2">
            <Sparkles className="text-primary size-5" />
            Set up with your AI
          </DialogTitle>
          <DialogDescription>
            Copy the prompt into claude.ai (or any chatbot) above your résumé
            and one sentence about what you want. Paste its reply back here.
          </DialogDescription>
        </DialogHeader>

        {/* Remount on each open so pane/reply state resets (old effect behavior). */}
        {open && (
          <AiSetupPanes
            key={String(open)}
            promptKind={promptKind}
            autorun={autorun}
            onApplied={onApplied}
            appliedExtra={appliedExtra}
            onDone={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function AppliedSummary({
  result,
  onDone,
  extra,
}: {
  result: AiSetupResult;
  onDone?: () => void;
  extra?: React.ReactNode;
}) {
  const applied = result.applied;
  const seedCount = result.kind === "full" ? result.seed_count : 0;
  const seedRow = showsSeedRow(result);
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
  // The seeds row only appears for the combined (full) reply, and only when it
  // actually carried starter companies (inclusion over precision: config-only
  // replies still apply cleanly — we just don't show a "0 companies" row).
  if (seedRow) {
    rows.push({
      label: "Starter companies",
      value: `${seedCount} to watch`,
    });
  }
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
      <div className="flex items-center justify-end gap-2">
        {extra}
        {onDone && (
          <Button size="sm" onClick={onDone}>
            Done
          </Button>
        )}
      </div>
    </>
  );
}
