import * as React from "react";
import { Loader2 } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";

/* A generic paste-a-reply dialog — the web twin of ui/paste_dialog.PasteDialog.
 * A titled textarea + Cancel/Submit; the parent owns the async submit (pass
 * `pending` for the spinner and keep the dialog open until it resolves). Used by the
 * Apply Queue (paste resume/batch/fit replies) and the Resume tab (paste reply).
 * The textarea resets whenever the dialog reopens. */

export interface PasteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: React.ReactNode;
  placeholder?: string;
  submitLabel?: string;
  rows?: number;
  pending?: boolean;
  /** Called with the trimmed textarea contents on submit. */
  onSubmit: (text: string) => void;
}

export function PasteDialog({
  open,
  onOpenChange,
  title,
  description,
  placeholder = "Paste the reply here…",
  submitLabel = "Submit",
  rows = 8,
  pending = false,
  onSubmit,
}: PasteDialogProps) {
  const [text, setText] = React.useState("");

  React.useEffect(() => {
    if (open) setText("");
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="zg-serif">{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>

        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={placeholder}
          rows={rows}
          className="text-sm"
          autoFocus
        />

        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={pending || !text.trim()}
            onClick={() => onSubmit(text)}
          >
            {pending && <Loader2 className="size-3.5 animate-spin" />}
            {submitLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
