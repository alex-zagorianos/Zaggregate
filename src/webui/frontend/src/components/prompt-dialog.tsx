import * as React from "react";
import { toast } from "sonner";
import { Copy, Check } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { copyText } from "@/lib/clipboard";

/* A read-only prompt dialog with a one-click Copy — the display half of the BYO-AI
 * bridge (paste the copied prompt into claude.ai, then paste the reply back through
 * a PasteDialog). Used by the Apply Queue (resume prompt, batch prompt, fit-rank
 * prompt) and the Resume tab. The prompt sits in a read-only textarea so the user
 * can also select/copy manually; Copy uses the clipboard helper with a legacy
 * fallback and flips to a check for a moment. */

export interface PromptDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: React.ReactNode;
  prompt: string;
  /** Optional content rendered above the prompt (e.g. an auto-filtered note). */
  children?: React.ReactNode;
}

export function PromptDialog({
  open,
  onOpenChange,
  title,
  description,
  prompt,
  children,
}: PromptDialogProps) {
  const [copied, setCopied] = React.useState(false);

  React.useEffect(() => {
    if (open) setCopied(false);
  }, [open]);

  const onCopy = async () => {
    const ok = await copyText(prompt);
    if (ok) {
      setCopied(true);
      toast.success("Prompt copied", {
        description: "Paste it into claude.ai, then paste the reply back here.",
      });
      window.setTimeout(() => setCopied(false), 1600);
    } else {
      toast.error("Couldn't copy", {
        description: "Select the text and copy it manually.",
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="zg-serif">{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>

        {children}

        <Textarea
          value={prompt}
          readOnly
          rows={12}
          className="zg-num text-xs"
          onFocus={(e) => e.currentTarget.select()}
        />

        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
          >
            Close
          </Button>
          <Button size="sm" onClick={onCopy}>
            {copied ? (
              <Check className="size-4" />
            ) : (
              <Copy className="size-4" />
            )}
            {copied ? "Copied" : "Copy prompt"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
