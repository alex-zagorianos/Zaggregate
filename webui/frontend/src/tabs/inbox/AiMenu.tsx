import * as React from "react";
import { toast } from "sonner";
import {
  Sparkles,
  Download,
  Upload,
  ClipboardPaste,
  Undo2,
  FileDown,
  Loader2,
  ChevronDown,
} from "lucide-react";

import {
  useExportInbox,
  useImportInbox,
  useScoreReply,
  useUndoRerank,
} from "@/api/queries";
import {
  downloadExport,
  ApiError,
  type ExportFmt,
  type ExportScope,
  type ExportViewFilters,
  type ExportFile,
  type ImportPolicy,
} from "@/api/client";
import { type InboxFilterState } from "@/lib/inbox-filter-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

/* "Rank with AI" — the BYO-AI round-trip menu. Four flows, each ending with the
 * inbox queries invalidated (handled by the query hooks):
 *   • Export for AI    → scope/format dialog → POST /export → file list + downloads
 *   • Import results   → file picker OR paste tab → POST /import → result summary
 *   • Paste AI reply   → textarea → POST /score-reply → applied/asked/missed toast
 *   • Undo last ranking→ confirm → POST /undo-rerank
 * The current filter state is passed so "Export view" re-applies exactly what the
 * user sees (server maps our snake_case filter payload). */

export interface AiMenuProps {
  filters: InboxFilterState;
}

type OpenDialog = "export" | "import" | "reply" | null;

export function AiMenu({ filters }: AiMenuProps) {
  const [dialog, setDialog] = React.useState<OpenDialog>(null);
  const [confirmUndo, setConfirmUndo] = React.useState(false);
  const undoRerank = useUndoRerank();

  const onUndo = () => {
    undoRerank.mutate(undefined, {
      onSuccess: (r) =>
        toast(r.restored > 0 ? "AI ranking undone" : "Nothing to undo", {
          description:
            r.restored > 0
              ? `Reverted ${r.restored} row${r.restored === 1 ? "" : "s"} to their previous scores.`
              : "There was no recent AI ranking to revert.",
        }),
      onError: (e) =>
        toast.error("Couldn't undo", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
    });
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" className="gap-1.5">
            <Sparkles className="text-primary size-4" />
            Rank with AI
            <ChevronDown className="size-3.5 opacity-70" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          <DropdownMenuLabel>Bring your own AI</DropdownMenuLabel>
          <DropdownMenuItem onSelect={() => setDialog("export")}>
            <Download className="size-4" />
            Export for AI…
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setDialog("import")}>
            <Upload className="size-4" />
            Import results…
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setDialog("reply")}>
            <ClipboardPaste className="size-4" />
            Paste AI reply…
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={() => setConfirmUndo(true)}
            className="text-muted-foreground"
          >
            <Undo2 className="size-4" />
            Undo last AI ranking
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <ExportDialog
        open={dialog === "export"}
        onOpenChange={(o) => !o && setDialog(null)}
        filters={filters}
      />
      <ImportDialog
        open={dialog === "import"}
        onOpenChange={(o) => !o && setDialog(null)}
      />
      <ReplyDialog
        open={dialog === "reply"}
        onOpenChange={(o) => !o && setDialog(null)}
      />

      <ConfirmDialog
        open={confirmUndo}
        onOpenChange={setConfirmUndo}
        title="Undo the last AI ranking?"
        description="This reverts the most recent AI re-rank across every route (file import, paste, or auto-rank), restoring the previous scores. Your jobs stay in the inbox."
        confirmLabel="Undo ranking"
        cancelLabel="Keep it"
        onConfirm={onUndo}
      />
    </>
  );
}

/** Map the frontend filter state → the server's snake_case export filter payload
 * (the export route re-applies these for scope='view'). */
function toExportFilters(s: InboxFilterState): ExportViewFilters {
  return {
    min_score: s.minScore ?? undefined,
    sources: s.sources.length ? s.sources : undefined,
    size: s.size !== "All" ? s.size : undefined,
    location_mode: s.locationMode,
    pay_floor: s.payFloor || undefined,
    q: s.q.trim() || undefined,
    new_only: s.newOnly || undefined,
    unscored_only: s.unscoredOnly || undefined,
    hide_stale: s.hideStale || undefined,
  };
}

// ── Export dialog ─────────────────────────────────────────────────────────────
function ExportDialog({
  open,
  onOpenChange,
  filters,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  filters: InboxFilterState;
}) {
  const [scope, setScope] = React.useState<ExportScope>("all");
  const [fmt, setFmt] = React.useState<ExportFmt>("both");
  const [compact, setCompact] = React.useState(false);
  const [files, setFiles] = React.useState<ExportFile[]>([]);
  const [count, setCount] = React.useState(0);
  const exportMut = useExportInbox();

  // Reset the result view whenever the dialog reopens.
  React.useEffect(() => {
    if (open) {
      setFiles([]);
      setCount(0);
    }
  }, [open]);

  const onExport = () => {
    exportMut.mutate(
      {
        scope,
        fmt,
        compact,
        filters: scope === "view" ? toExportFilters(filters) : undefined,
      },
      {
        onSuccess: (res) => {
          setFiles(res.files);
          setCount(res.count);
          toast.success("Export ready", {
            description: `${res.count} job${res.count === 1 ? "" : "s"} written — download and hand to your AI.`,
          });
        },
        onError: (e) =>
          toast.error("Couldn't export", {
            description:
              e instanceof ApiError ? e.message : "Nothing to export.",
          }),
      },
    );
  };

  const onDownload = (f: ExportFile) => {
    const base = f.name.split("/").pop() || f.name;
    downloadExport(f.download_url, base).catch((e) =>
      toast.error("Download failed", {
        description: e instanceof ApiError ? e.message : "Please try again.",
      }),
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="zg-serif">Export for AI ranking</DialogTitle>
          <DialogDescription>
            Write your inbox to a file, hand it to any AI with the included
            prompt, then import the results back.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-muted-foreground text-xs">Scope</Label>
            <div className="flex gap-2">
              <RadioPill
                active={scope === "all"}
                onClick={() => setScope("all")}
                label="Whole inbox"
              />
              <RadioPill
                active={scope === "view"}
                onClick={() => setScope("view")}
                label="Current view (filtered)"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label
                htmlFor="export-fmt"
                className="text-muted-foreground text-xs"
              >
                Format
              </Label>
              <Select
                id="export-fmt"
                value={fmt}
                onChange={(e) => setFmt(e.target.value as ExportFmt)}
              >
                <option value="both">CSV + Markdown</option>
                <option value="csv">CSV only</option>
                <option value="md">Markdown only</option>
              </Select>
            </div>
            <div className="flex items-end">
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={compact}
                  onChange={(e) => setCompact(e.target.checked)}
                  className="accent-[var(--zg-accent)]"
                />
                <span className="text-foreground">Compact</span>
              </label>
            </div>
          </div>

          {files.length > 0 && (
            <div className="border-border space-y-1.5 rounded-md border p-2">
              <p className="text-muted-foreground zg-num text-xs">
                {count} job{count === 1 ? "" : "s"} · {files.length} file
                {files.length === 1 ? "" : "s"}
              </p>
              {files.map((f) => (
                <button
                  key={f.name}
                  type="button"
                  onClick={() => onDownload(f)}
                  className="hover:bg-accent flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm transition-colors"
                >
                  <FileDown className="text-primary size-4 shrink-0" />
                  <span className="zg-num truncate">
                    {f.name.split("/").pop()}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
          >
            {files.length > 0 ? "Done" : "Cancel"}
          </Button>
          <Button size="sm" onClick={onExport} disabled={exportMut.isPending}>
            {exportMut.isPending && (
              <Loader2 className="size-3.5 animate-spin" />
            )}
            {files.length > 0 ? "Re-export" : "Export"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Import dialog ─────────────────────────────────────────────────────────────
function ImportDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const [tab, setTab] = React.useState<"file" | "paste">("file");
  const [file, setFile] = React.useState<File | null>(null);
  const [text, setText] = React.useState("");
  const [policy, setPolicy] = React.useState<ImportPolicy>("overwrite");
  const importMut = useImportInbox();

  React.useEffect(() => {
    if (open) {
      setFile(null);
      setText("");
    }
  }, [open]);

  const onImport = () => {
    const input =
      tab === "file" ? (file ? { file } : null) : text.trim() ? { text } : null;
    if (!input) {
      toast("Nothing to import", {
        description:
          tab === "file"
            ? "Choose a file first."
            : "Paste the AI results first.",
      });
      return;
    }
    importMut.mutate(
      { input, policy },
      {
        onSuccess: (res) => {
          const r = res.result;
          const desc =
            `${r.updated} updated, ${r.matched} matched` +
            (r.unmatched ? `, ${r.unmatched} unmatched` : "") +
            (r.errors.length ? ` · ${r.errors.length} error(s)` : "");
          if (r.errors.length && r.updated === 0) {
            toast.error("Import had problems", { description: r.errors[0] });
          } else {
            toast.success("Imported AI scores", { description: desc });
            onOpenChange(false);
          }
        },
        onError: (e) =>
          toast.error("Couldn't import", {
            description:
              e instanceof ApiError
                ? e.message
                : "Check the file and try again.",
          }),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="zg-serif">Import AI results</DialogTitle>
          <DialogDescription>
            Load the scored file (or paste it) your AI returned. Scores land on
            the matching inbox rows.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex gap-2">
            <RadioPill
              active={tab === "file"}
              onClick={() => setTab("file")}
              label="Upload file"
            />
            <RadioPill
              active={tab === "paste"}
              onClick={() => setTab("paste")}
              label="Paste text"
            />
          </div>

          {tab === "file" ? (
            <div className="space-y-1.5">
              <Label
                htmlFor="import-file"
                className="text-muted-foreground text-xs"
              >
                CSV or JSON file
              </Label>
              <Input
                id="import-file"
                type="file"
                accept=".csv,.json,text/csv,application/json"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="file:text-foreground cursor-pointer"
              />
              {file && (
                <p className="text-muted-foreground zg-num text-xs">
                  {file.name}
                </p>
              )}
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label
                htmlFor="import-text"
                className="text-muted-foreground text-xs"
              >
                Paste the CSV / JSON the AI returned
              </Label>
              <Textarea
                id="import-text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="job_key,fit,fit_why…"
                rows={6}
                className="zg-num text-xs"
              />
            </div>
          )}

          <div className="space-y-1.5">
            <Label
              htmlFor="import-policy"
              className="text-muted-foreground text-xs"
            >
              When a row already has a score
            </Label>
            <Select
              id="import-policy"
              value={policy}
              onChange={(e) => setPolicy(e.target.value as ImportPolicy)}
            >
              <option value="overwrite">Overwrite existing scores</option>
              <option value="keep_existing">Keep existing, fill blanks</option>
              <option value="add_only">Only add to unscored rows</option>
            </Select>
          </div>
        </div>

        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button size="sm" onClick={onImport} disabled={importMut.isPending}>
            {importMut.isPending && (
              <Loader2 className="size-3.5 animate-spin" />
            )}
            Import
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Paste-reply dialog ────────────────────────────────────────────────────────
function ReplyDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const [text, setText] = React.useState("");
  const scoreReply = useScoreReply();

  React.useEffect(() => {
    if (open) setText("");
  }, [open]);

  const onApply = () => {
    if (!text.trim()) {
      toast("Nothing to apply", { description: "Paste the AI reply first." });
      return;
    }
    scoreReply.mutate(text, {
      onSuccess: (r) => {
        toast.success("Scores applied", {
          description: `${r.applied} of ${r.asked} asked applied${r.missed ? `, ${r.missed} missed` : ""}.`,
        });
        onOpenChange(false);
      },
      onError: (e) =>
        toast.error("Couldn't read the reply", {
          description:
            e instanceof ApiError ? e.message : "Check the format and retry.",
        }),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="zg-serif">Paste an AI reply</DialogTitle>
          <DialogDescription>
            Paste the AI's fit reply for the batch you asked it to rank. Scores
            are applied to the matching unscored rows.
          </DialogDescription>
        </DialogHeader>

        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste the AI's reply here…"
          rows={8}
          className="text-sm"
        />

        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button size="sm" onClick={onApply} disabled={scoreReply.isPending}>
            {scoreReply.isPending && (
              <Loader2 className="size-3.5 animate-spin" />
            )}
            Apply scores
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function RadioPill({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      onClick={onClick}
      className={cn(
        "rounded-[var(--radius-chip)] border px-3 py-1.5 text-sm font-medium transition-colors",
        "focus-visible:ring-ring/50 outline-none focus-visible:ring-2",
        active
          ? "border-primary/50 bg-primary/12 text-primary"
          : "border-border text-muted-foreground hover:text-foreground",
      )}
    >
      {label}
    </button>
  );
}
