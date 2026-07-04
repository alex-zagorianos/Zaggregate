import * as React from "react";
import { toast } from "sonner";
import { FileText, Wand2, Loader2, ArrowLeftRight } from "lucide-react";

import { endpoints, ApiError } from "@/api/client";
import type { WizardAnswers } from "@/lib/wizard-steps";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { StepHead } from "./StepHead";

/* Step 5 — Résumé (optional). Paste plain-text résumé; a "Preview structure"
 * button runs it through /onboarding/resume-structure (the auto-structurer that
 * makes a raw paste safe for scoring) and shows a before/after so the user sees
 * what changed before it's saved on Finish. Nothing is written here — the wizard
 * carries the raw text and applies it on Finish. */

export function ResumeStep({
  answers,
  patch,
}: {
  answers: WizardAnswers;
  patch: (p: Partial<WizardAnswers>) => void;
}) {
  const [preview, setPreview] = React.useState<string | null>(null);
  const [restructured, setRestructured] = React.useState(false);
  const [loading, setLoading] = React.useState(false);

  const text = answers.resumeText;

  const onPreview = () => {
    if (!text.trim()) return;
    setLoading(true);
    endpoints
      .structureResume(text)
      .then((r) => {
        setPreview(r.markdown);
        setRestructured(r.restructured);
        if (!r.restructured)
          toast("Already well-structured", {
            description: "Your résumé is ready as-is.",
          });
      })
      .catch((e) =>
        toast.error("Couldn't preview", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
      )
      .finally(() => setLoading(false));
  };

  return (
    <div className="max-w-2xl">
      <StepHead
        icon={<FileText className="size-4" />}
        eyebrow="Your background"
        title="Paste your résumé"
        sub="Optional, but it sharpens every score and powers one-click résumé tailoring later. Plain text is fine — we tidy it up automatically."
      />

      <div className="mt-8 space-y-4">
        <Textarea
          value={text}
          onChange={(e) => {
            patch({ resumeText: e.target.value });
            setPreview(null);
          }}
          placeholder="Paste your résumé here (plain text is fine)…"
          rows={10}
          className="text-sm"
        />

        <div className="flex items-center justify-between gap-3">
          <p className="text-muted-foreground text-xs">
            {text.trim()
              ? `${text.trim().length.toLocaleString()} characters`
              : "You can skip this and add it later."}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={onPreview}
            disabled={loading || !text.trim()}
          >
            {loading ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Wand2 className="size-3.5" />
            )}
            Preview structure
          </Button>
        </div>

        {preview !== null && (
          <div className="border-border bg-card/60 space-y-2 rounded-lg border p-4">
            <div className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
              <ArrowLeftRight className="size-3.5" />
              {restructured
                ? "We reformatted it for scoring — here's the tidied version:"
                : "Already clean — this is what we'll use:"}
            </div>
            <pre className="text-foreground/90 max-h-56 overflow-auto text-xs leading-relaxed whitespace-pre-wrap">
              {preview || "(empty)"}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
