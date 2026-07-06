import * as React from "react";
import { toast } from "sonner";
import {
  FileText,
  Copy,
  Check,
  ClipboardPaste,
  Sparkles,
  Loader2,
  RotateCcw,
} from "lucide-react";

import { endpoints, ApiError, type BundleFile } from "@/api/client";
import { copyText } from "@/lib/clipboard";
import { FileDownloads } from "@/components/file-downloads";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

/* Resume — the standalone paste-a-posting → tailored DOCX generator, the web twin
 * of ui/tab_resume.ResumeTab. A two-step card flow:
 *   1. Paste a job posting → Copy prompt (build via /resume/prompt, then copy for
 *      claude.ai).
 *   2. Paste the reply → resume + cover-letter Word docs via /resume/from-paste,
 *      returned as gated downloads (replacing the tk "reveal in explorer" — repo
 *      rule: HTTP downloads only).
 *
 * The backend exposes exactly these two routes (/resume/prompt + /resume/from-paste);
 * there is NO standalone server-side "generate" route for this tab, so it's a pure
 * copy-prompt bridge — matching the tk ResumeTab, whose one-shot API generate is the
 * inline Apply-Queue flow, not this screen. No dead "Generate via API" button here. */

export function ResumeTab() {
  const [posting, setPosting] = React.useState("");
  const [prompt, setPrompt] = React.useState("");
  const [copied, setCopied] = React.useState(false);
  const [reply, setReply] = React.useState("");
  const [building, setBuilding] = React.useState(false);
  const [promptLoading, setPromptLoading] = React.useState(false);
  const [files, setFiles] = React.useState<BundleFile[]>([]);

  const onCopyPrompt = () => {
    const text = posting.trim();
    if (!text) {
      toast("Paste a posting first", {
        description: "Paste the job posting text above to build a prompt.",
      });
      return;
    }
    setPromptLoading(true);
    endpoints
      .resumePrompt(text)
      .then(async (r) => {
        setPrompt(r.prompt);
        const ok = await copyText(r.prompt);
        if (ok) {
          setCopied(true);
          toast.success("Prompt copied", {
            description:
              "Paste it into claude.ai, then paste the reply below for your DOCX.",
          });
          window.setTimeout(() => setCopied(false), 1600);
        } else {
          toast("Prompt ready", {
            description:
              "Couldn't auto-copy — select it below and copy manually.",
          });
        }
      })
      .catch((e) =>
        toast.error("Couldn't build the prompt", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
      )
      .finally(() => setPromptLoading(false));
  };

  const onBuildDocs = () => {
    const text = reply.trim();
    if (!text) {
      toast("Paste the reply first", {
        description: "Paste claude.ai's reply to get your Word documents.",
      });
      return;
    }
    setBuilding(true);
    endpoints
      .resumeFromPaste(text, posting.trim() || undefined)
      .then((r) => {
        setFiles(r.files);
        toast.success("Documents ready", {
          description: "Your resume and cover letter are ready to download.",
        });
      })
      .catch((e) =>
        toast.error("Couldn't build the documents", {
          description:
            e instanceof ApiError ? e.message : "Check the reply and retry.",
        }),
      )
      .finally(() => setBuilding(false));
  };

  const onReset = () => {
    setPosting("");
    setPrompt("");
    setReply("");
    setFiles([]);
    setCopied(false);
  };

  return (
    <section aria-labelledby="resume-heading" className="flex h-full flex-col">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1
            id="resume-heading"
            className="zg-serif text-foreground flex items-center gap-2.5 text-2xl font-semibold tracking-tight"
          >
            <FileText className="text-primary size-6" strokeWidth={2} />
            Resume
          </h1>
          <p className="text-muted-foreground max-w-xl text-sm leading-relaxed">
            Paste a job posting, copy the tailoring prompt into claude.ai, then
            paste the reply to get a tailored resume + cover letter as Word
            docs.
          </p>
        </div>
        {(posting || reply || files.length > 0) && (
          <Button variant="ghost" size="sm" onClick={onReset}>
            <RotateCcw className="size-3.5" />
            Start over
          </Button>
        )}
      </div>

      {/* Two-step flow */}
      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Step 1 — posting → prompt */}
        <StepCard step={1} title="Paste the job posting">
          <div className="space-y-1.5">
            <Label htmlFor="resume-posting" className="sr-only">
              Job posting
            </Label>
            <Textarea
              id="resume-posting"
              value={posting}
              onChange={(e) => setPosting(e.target.value)}
              placeholder="Paste the full job posting text here…"
              rows={10}
              className="text-sm"
            />
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              onClick={onCopyPrompt}
              disabled={promptLoading || !posting.trim()}
            >
              {promptLoading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : copied ? (
                <Check className="size-4" />
              ) : (
                <Copy className="size-4" />
              )}
              {copied ? "Copied" : "Copy prompt"}
            </Button>
            <span className="text-muted-foreground inline-flex items-center gap-1 text-xs">
              <Sparkles className="size-3.5" />
              Paste into claude.ai
            </span>
          </div>
          {prompt && (
            <div className="space-y-1.5">
              <p className="text-muted-foreground text-xs font-medium">
                Prompt (copy again if needed)
              </p>
              <Textarea
                value={prompt}
                readOnly
                rows={5}
                className="zg-num text-xs"
                onFocus={(e) => e.currentTarget.select()}
              />
            </div>
          )}
        </StepCard>

        {/* Step 2 — reply → DOCX */}
        <StepCard step={2} title="Paste claude.ai's reply">
          <div className="space-y-1.5">
            <Label htmlFor="resume-reply" className="sr-only">
              claude.ai reply
            </Label>
            <Textarea
              id="resume-reply"
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              placeholder="Paste the reply from claude.ai here…"
              rows={10}
              className="text-sm"
            />
          </div>
          <Button
            size="sm"
            onClick={onBuildDocs}
            disabled={building || !reply.trim()}
          >
            {building ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <ClipboardPaste className="size-4" />
            )}
            Build resume + cover letter
          </Button>

          {files.length > 0 ? (
            <div className="border-border bg-secondary/30 space-y-2 rounded-md border p-3">
              <FileDownloads files={files} label="Documents ready" />
              <p className="text-muted-foreground text-xs leading-relaxed">
                Saved to your project's output folder. Download the Word files
                above, review, and submit with your application.
              </p>
            </div>
          ) : (
            <p className="text-muted-foreground text-xs leading-relaxed">
              Your tailored resume and cover letter appear here as downloadable
              Word documents.
            </p>
          )}
        </StepCard>
      </div>
    </section>
  );
}

function StepCard({
  step,
  title,
  children,
}: {
  step: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="border-border bg-card flex flex-col gap-3 rounded-lg border p-4">
      <div className="flex items-center gap-2.5">
        <span
          className={cn(
            "zg-num flex size-6 shrink-0 items-center justify-center rounded-full text-sm font-semibold",
            "bg-primary/12 text-primary border-primary/30 border",
          )}
        >
          {step}
        </span>
        <h2 className="zg-serif text-foreground text-base font-semibold tracking-tight">
          {title}
        </h2>
      </div>
      {children}
    </div>
  );
}
