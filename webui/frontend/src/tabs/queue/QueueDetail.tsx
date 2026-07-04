import * as React from "react";
import { toast } from "sonner";
import {
  Building2,
  MapPin,
  Wallet,
  ExternalLink,
  CheckCircle2,
  XCircle,
  Copy,
  ClipboardPaste,
  Sparkles,
  Users,
  FileSearch,
  MousePointerClick,
  Loader2,
} from "lucide-react";

import {
  endpoints,
  ApiError,
  type QueueRow,
  type BundleFile,
} from "@/api/client";
import { ScoreChip } from "@/components/score-chip";
import { PromptDialog } from "@/components/prompt-dialog";
import { PasteDialog } from "@/components/paste-dialog";
import { FileDownloads } from "@/components/file-downloads";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

/* The Apply Queue detail rail — the selected job's second surface. Header (title /
 * company / meta + fit chip + Track/Open/Dismiss), then the AI fit rationale, the
 * ATS hint, and the referral nudge (all engine-computed, no network). Below that the
 * doc actions: Copy resume prompt (→ PromptDialog), Paste reply → DOCX
 * (→ PasteDialog → download buttons), Generate via API. Empty until a row is picked.
 *
 * Generate via API: no client-side api-availability probe exists, so the button is
 * always shown; a 409 {error:"no api key"} from /generate surfaces a clear toast
 * telling the user to set the key (server-side; the key never leaves the server). */

export interface QueueDetailProps {
  row: QueueRow | null;
  onMarkApplied: (row: QueueRow) => void;
  onDismiss: (row: QueueRow) => void;
  onOpen: (row: QueueRow) => void;
  /** Called after docs are saved (paste or generate) so the tab refetches. */
  onDocsSaved: () => void;
}

function fitValue(row: QueueRow): number | null | undefined {
  const f = row.fit_score;
  if (typeof f === "number" && f >= 0) return f;
  return row.score;
}

export function QueueDetail({
  row,
  onMarkApplied,
  onDismiss,
  onOpen,
  onDocsSaved,
}: QueueDetailProps) {
  const [promptText, setPromptText] = React.useState<string | null>(null);
  const [pasteOpen, setPasteOpen] = React.useState(false);
  const [pastePending, setPastePending] = React.useState(false);
  const [generating, setGenerating] = React.useState(false);
  const [savedFiles, setSavedFiles] = React.useState<BundleFile[]>([]);

  // Reset the transient doc state when the selected job changes.
  React.useEffect(() => {
    setPromptText(null);
    setPasteOpen(false);
    setSavedFiles([]);
  }, [row?.id]);

  if (!row) {
    return (
      <div className="flex min-h-[46vh] flex-col items-center justify-center px-6 text-center">
        <MousePointerClick
          className="text-muted-foreground/40 mb-4 size-10"
          strokeWidth={1.25}
        />
        <p className="zg-serif text-foreground text-lg font-medium">
          Select a job
        </p>
        <p className="text-muted-foreground mt-1.5 max-w-xs text-sm leading-relaxed">
          Pick a job to see its fit rationale and tailor a resume — copy a
          prompt, paste the reply, and download the docs.
        </p>
      </div>
    );
  }

  const jobId = row.id;

  const onCopyPrompt = () => {
    endpoints
      .queueResumePrompt(jobId)
      .then((r) => setPromptText(r.prompt))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 400) {
          toast("No saved posting", {
            description:
              "This job has no saved description — use the Resume tab to paste the posting.",
          });
        } else {
          toast.error("Couldn't build the prompt", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          });
        }
      });
  };

  const onPasteSubmit = (text: string) => {
    setPastePending(true);
    endpoints
      .queueResumeFromPaste(jobId, text)
      .then((r) => {
        setSavedFiles(r.files);
        setPasteOpen(false);
        toast.success("Documents ready", {
          description: "Your tailored resume is saved — download it below.",
        });
        onDocsSaved();
      })
      .catch((e) =>
        toast.error("Couldn't build the docs", {
          description:
            e instanceof ApiError ? e.message : "Check the reply and retry.",
        }),
      )
      .finally(() => setPastePending(false));
  };

  const onGenerate = () => {
    setGenerating(true);
    endpoints
      .queueGenerate(jobId)
      .then((r) => {
        setSavedFiles(r.files);
        toast.success("Generated with AI", {
          description: "Your tailored resume is saved — download it below.",
        });
        onDocsSaved();
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 409) {
          const err = e.message.toLowerCase();
          if (err.includes("key")) {
            toast("No API key configured", {
              description:
                "Set an Anthropic API key on the server to generate directly, or use Copy prompt → claude.ai instead.",
            });
          } else {
            toast("Already generating", {
              description: "A generate or ranking is already running.",
            });
          }
        } else {
          toast.error("Couldn't generate", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          });
        }
      })
      .finally(() => setGenerating(false));
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-border border-b px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="zg-serif text-foreground text-lg leading-tight font-semibold tracking-tight">
              {row.title || "Untitled role"}
            </h2>
            <p className="text-muted-foreground mt-0.5 flex items-center gap-1.5 text-sm">
              <Building2 className="size-3.5 shrink-0" />
              <span className="truncate">
                {row.company || "Unknown company"}
              </span>
            </p>
          </div>
          <ScoreChip value={fitValue(row)} />
        </div>

        <div className="text-muted-foreground mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
          <span className="flex items-center gap-1">
            <MapPin className="size-3.5" />
            {row.location || "—"}
          </span>
          {row.salary_text && (
            <span className="zg-num flex items-center gap-1">
              <Wallet className="size-3.5" />
              {row.salary_text}
            </span>
          )}
        </div>

        <div className="mt-4 flex items-center gap-2">
          <Button size="sm" onClick={() => onMarkApplied(row)}>
            <CheckCircle2 className="size-4" />
            Mark applied
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => onOpen(row)}
            disabled={!row.url}
          >
            <ExternalLink className="size-4" />
            Open
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onDismiss(row)}
            className="text-muted-foreground hover:text-destructive"
          >
            <XCircle className="size-4" />
            Dismiss
          </Button>
        </div>
      </div>

      {/* Scrolling body */}
      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4">
        {row.ats_label && (
          <MetaLine
            icon={<FileSearch className="size-3.5" />}
            label="Applies through"
            value={row.ats_label}
          />
        )}
        {row.referral && (
          <MetaLine
            icon={<Users className="size-3.5" />}
            label="Referral"
            value={row.referral}
            tone="accent"
          />
        )}

        <FitWhy fit={fitValue(row)} why={row.fit_rationale} />

        {/* Doc actions */}
        <section className="space-y-2.5">
          <h3 className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
            Tailored documents
          </h3>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={onCopyPrompt}>
              <Copy className="size-4" />
              Copy resume prompt
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setPasteOpen(true)}
            >
              <ClipboardPaste className="size-4" />
              Paste reply → DOCX
            </Button>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={onGenerate}
                  disabled={generating}
                >
                  {generating ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Sparkles className="text-primary size-4" />
                  )}
                  Generate via API
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                Generate on the server with your Anthropic key (if configured).
              </TooltipContent>
            </Tooltip>
          </div>
          <FileDownloads files={savedFiles} label="Documents ready" />
        </section>
      </div>

      {/* Prompt display */}
      <PromptDialog
        open={promptText !== null}
        onOpenChange={(o) => !o && setPromptText(null)}
        title="Resume tailoring prompt"
        description="Paste this into claude.ai, then paste the reply back with “Paste reply → DOCX”."
        prompt={promptText ?? ""}
      />

      {/* Paste reply */}
      <PasteDialog
        open={pasteOpen}
        onOpenChange={setPasteOpen}
        title="Paste the claude.ai reply"
        description="Paste the reply to the resume prompt — a tailored resume and cover letter are built as Word documents."
        placeholder="Paste the reply here…"
        submitLabel="Build documents"
        pending={pastePending}
        onSubmit={onPasteSubmit}
      />
    </div>
  );
}

function MetaLine({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone?: "accent";
}) {
  return (
    <div className="flex items-start gap-2 text-sm">
      <span
        className={
          tone === "accent"
            ? "text-primary mt-0.5"
            : "text-muted-foreground mt-0.5"
        }
      >
        {icon}
      </span>
      <p className="leading-relaxed">
        <span className="text-muted-foreground">{label}: </span>
        <span
          className={tone === "accent" ? "text-primary/90" : "text-foreground"}
        >
          {value}
        </span>
      </p>
    </div>
  );
}

function FitWhy({
  fit,
  why,
}: {
  fit: number | null | undefined;
  why: string | null | undefined;
}) {
  const text = (why ?? "").trim();
  return (
    <section className="space-y-2">
      <h3 className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
        Why it matched
      </h3>
      <div className="flex items-start gap-2.5">
        <ScoreChip value={fit} />
        <p className="text-foreground/90 flex-1 text-sm leading-relaxed">
          {text || (
            <span className="text-muted-foreground">
              No AI rationale yet — rank the queue with AI to get one.
            </span>
          )}
        </p>
      </div>
    </section>
  );
}
