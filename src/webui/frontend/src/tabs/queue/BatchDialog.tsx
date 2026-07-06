import * as React from "react";
import { toast } from "sonner";
import {
  Copy,
  Check,
  ClipboardPaste,
  Loader2,
  CheckCircle2,
  XCircle,
  CircleDashed,
} from "lucide-react";

import {
  endpoints,
  ApiError,
  type QueueRow,
  type BundleFile,
} from "@/api/client";
import {
  mapBatchResults,
  batchSummaryLine,
  type BatchOutcome,
} from "@/lib/batch-result";
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
import { FileDownloads } from "@/components/file-downloads";
import { cn } from "@/lib/utils";

/* The batch resume round-trip — one prompt covering the next 5 queued jobs that
 * still need docs (with a saved description), then a single paste reply → per-job
 * DOCX bundles.
 *
 * Step 1: /queue/batch-prompt returns the prompt + the ordered `ids` (reply slot N
 * maps to ids[N-1]). We show the prompt with a Copy button. Step 2: the user pastes
 * the multi-job reply; /queue/batch-from-paste returns per-job results, which
 * batch-result.mapBatchResults folds against the ids + rows into a per-row outcome
 * list (saved / failed / missing) with download buttons + the tk-style summary. */

export interface BatchDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rows: QueueRow[];
  /** Called after a batch save so the tab refetches (docs landed on jobs). */
  onDone: () => void;
}

export function BatchDialog({
  open,
  onOpenChange,
  rows,
  onDone,
}: BatchDialogProps) {
  const [loading, setLoading] = React.useState(false);
  const [prompt, setPrompt] = React.useState("");
  const [ids, setIds] = React.useState<number[]>([]);
  const [copied, setCopied] = React.useState(false);
  const [reply, setReply] = React.useState("");
  const [pasting, setPasting] = React.useState(false);
  const [outcomes, setOutcomes] = React.useState<BatchOutcome[] | null>(null);

  // Build the batch prompt whenever the dialog opens (fresh each time).
  React.useEffect(() => {
    if (!open) return;
    setPrompt("");
    setIds([]);
    setReply("");
    setOutcomes(null);
    setCopied(false);
    setLoading(true);
    endpoints
      .queueBatchPrompt()
      .then((r) => {
        setPrompt(r.prompt);
        setIds(r.ids);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 400) {
          toast("Nothing to batch", {
            description:
              "No queued jobs with a saved description still need docs.",
          });
          onOpenChange(false);
        } else {
          toast.error("Couldn't build the batch prompt", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          });
          onOpenChange(false);
        }
      })
      .finally(() => setLoading(false));
    // Deps intentionally just [open] — rebuild once per dialog open.
  }, [open]);

  const onCopy = async () => {
    const ok = await copyText(prompt);
    if (ok) {
      setCopied(true);
      toast.success("Batch prompt copied", {
        description: "Paste it into claude.ai, then paste the reply below.",
      });
      window.setTimeout(() => setCopied(false), 1600);
    } else {
      toast.error("Couldn't copy", {
        description: "Select the text and copy it manually.",
      });
    }
  };

  const onPaste = () => {
    if (!reply.trim()) {
      toast("Nothing to apply", {
        description: "Paste the batch reply first.",
      });
      return;
    }
    setPasting(true);
    endpoints
      .queueBatchFromPaste(reply, ids)
      .then((r) => {
        const mapped = mapBatchResults(ids, r.results, rows);
        setOutcomes(mapped);
        const line = batchSummaryLine(mapped);
        toast.success("Batch processed", { description: line });
        onDone();
      })
      .catch((e) =>
        toast.error("Couldn't process the batch", {
          description:
            e instanceof ApiError ? e.message : "Check the reply and retry.",
        }),
      )
      .finally(() => setPasting(false));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="zg-serif">
            Batch resume prompt ({ids.length || 5})
          </DialogTitle>
          <DialogDescription>
            One prompt for the next few queued jobs that need docs. Copy it,
            paste into claude.ai, then paste the whole reply back — each job's
            resume is built at once.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="text-muted-foreground flex items-center gap-2 py-8 text-sm">
            <Loader2 className="size-4 animate-spin" />
            Building the batch prompt…
          </div>
        ) : (
          <div className="space-y-4">
            {/* Step 1 — prompt */}
            <div className="space-y-1.5">
              <p className="text-muted-foreground text-xs font-medium">
                1 · Copy this prompt
              </p>
              <Textarea
                value={prompt}
                readOnly
                rows={7}
                className="zg-num text-xs"
                onFocus={(e) => e.currentTarget.select()}
              />
              <Button size="sm" variant="outline" onClick={onCopy}>
                {copied ? (
                  <Check className="size-4" />
                ) : (
                  <Copy className="size-4" />
                )}
                {copied ? "Copied" : "Copy prompt"}
              </Button>
            </div>

            {/* Step 2 — reply */}
            <div className="space-y-1.5">
              <p className="text-muted-foreground text-xs font-medium">
                2 · Paste the reply
              </p>
              <Textarea
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                placeholder="Paste the full batch reply from claude.ai here…"
                rows={5}
                className="text-sm"
              />
              <Button size="sm" onClick={onPaste} disabled={pasting}>
                {pasting ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <ClipboardPaste className="size-4" />
                )}
                Build documents
              </Button>
            </div>

            {/* Results */}
            {outcomes && <BatchResults outcomes={outcomes} />}
          </div>
        )}

        <div className="flex justify-end">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
          >
            {outcomes ? "Done" : "Close"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function BatchResults({ outcomes }: { outcomes: BatchOutcome[] }) {
  return (
    <div className="border-border space-y-2 rounded-md border p-3">
      <p className="text-muted-foreground text-xs font-medium">
        {batchSummaryLine(outcomes)}
      </p>
      <ul className="space-y-2">
        {outcomes.map((o) => (
          <li key={o.id} className="space-y-1">
            <div className="flex items-center gap-2 text-sm">
              <OutcomeIcon kind={o.kind} />
              <span className="text-foreground truncate font-medium">
                {o.title || `Job #${o.id}`}
              </span>
              <span className="text-muted-foreground truncate text-xs">
                {o.company}
              </span>
            </div>
            {o.kind === "saved" && (
              <FileDownloads files={o.files as BundleFile[]} className="pl-6" />
            )}
            {o.kind === "failed" && (
              <p className="text-destructive pl-6 text-xs">{o.error}</p>
            )}
            {o.kind === "missing" && (
              <p className="text-muted-foreground pl-6 text-xs">
                No matching slot in the reply — re-paste or run this one singly.
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function OutcomeIcon({ kind }: { kind: BatchOutcome["kind"] }) {
  if (kind === "saved")
    return (
      <CheckCircle2
        className={cn("size-4 shrink-0 text-[var(--zg-success)]")}
      />
    );
  if (kind === "failed")
    return <XCircle className="text-destructive size-4 shrink-0" />;
  return <CircleDashed className="text-muted-foreground size-4 shrink-0" />;
}
