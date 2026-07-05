import * as React from "react";
import { toast } from "sonner";
import {
  Users,
  Upload,
  Trash2,
  Copy,
  Check,
  Loader2,
  ShieldCheck,
} from "lucide-react";

import {
  useNetworkSummary,
  useNetworkImport,
  useNetworkClear,
} from "@/api/queries";
import { ApiError } from "@/api/client";
import { friendlyError } from "@/lib/friendly-error";
import { copyText } from "@/lib/clipboard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/alert-dialog";

/* "Your network (local)" — the referral-contact import card on the Sources tab
 * (B4). The user picks a LinkedIn/Google CSV; we read it CLIENT-SIDE (FileReader)
 * and POST only the text. It never leaves the machine — the contacts live in a
 * local file under the data folder, matched against job companies to surface "N
 * people you know work here" in the Inbox/JobDialog. Shows the current summary, a
 * clear button, a privacy one-liner, and a copyable "how to export from LinkedIn"
 * hint. Deliberately self-contained so the whole feature is one-commit removable. */

// LinkedIn's own path to the connections export — copyable so the user can follow
// it in their own account.
const LINKEDIN_STEPS =
  "LinkedIn → Settings & Privacy → Data privacy → Get a copy of your data → " +
  "pick “Connections” → Request archive. You'll get a Connections.csv by email.";

const MAX_FILE_BYTES = 5 * 1024 * 1024;

export function NetworkImportCard() {
  const summary = useNetworkSummary();
  const importMut = useNetworkImport();
  const clearMut = useNetworkClear();
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [source, setSource] = React.useState<"linkedin" | "google">("linkedin");
  const [confirmClear, setConfirmClear] = React.useState(false);
  const [copied, setCopied] = React.useState(false);

  const total = summary.data?.total ?? 0;
  const companies = summary.data?.companies ?? 0;
  const lastImport = summary.data?.last_import ?? null;

  const onPick = () => fileRef.current?.click();

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-picking the same file
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) {
      toast.error("That file is too large", {
        description: "Connections exports are well under 5 MB.",
      });
      return;
    }
    const reader = new FileReader();
    reader.onerror = () =>
      toast.error("Couldn't read that file", {
        description: "Try exporting it again.",
      });
    reader.onload = () => {
      const text = String(reader.result ?? "");
      if (!text.trim()) {
        toast.error("That file looks empty");
        return;
      }
      importMut.mutate(
        { text, source },
        {
          onSuccess: (r) =>
            toast.success(
              r.added > 0
                ? `Added ${r.added} contact${r.added === 1 ? "" : "s"}`
                : "Nothing new to add",
              {
                description:
                  r.added > 0
                    ? `${r.total} total — we'll flag jobs at companies you know.`
                    : "Those contacts were already imported.",
              },
            ),
          onError: (err) =>
            toast.error("Couldn't import that file", {
              description: friendlyError(err),
            }),
        },
      );
    };
    reader.readAsText(file);
  };

  const onClear = () =>
    clearMut.mutate(undefined, {
      onSuccess: (r) =>
        toast.success(
          `Cleared ${r.removed} contact${r.removed === 1 ? "" : "s"}`,
        ),
      onError: (e) =>
        toast.error("Couldn't clear", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
    });

  const onCopySteps = async () => {
    const ok = await copyText(LINKEDIN_STEPS);
    if (ok) {
      setCopied(true);
      toast.success("Steps copied");
      window.setTimeout(() => setCopied(false), 1600);
    }
  };

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <Users className="text-primary size-5" strokeWidth={2} />
            Your network (local)
          </CardTitle>
          {total > 0 && (
            <span className="border-[var(--zg-success)]/40 bg-[var(--zg-success)]/12 text-[var(--zg-success)] inline-flex shrink-0 items-center gap-1.5 rounded-[var(--radius-chip)] border px-2 py-0.5 text-xs font-medium">
              <span className="zg-num">{total}</span> imported
            </span>
          )}
        </div>
        <p className="text-muted-foreground text-sm leading-relaxed">
          Import your LinkedIn or Google contacts to spot jobs at companies
          where you already know someone — a referral is the highest-conversion
          way in.
        </p>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Summary line */}
        {total > 0 ? (
          <p className="text-muted-foreground text-sm">
            <span className="zg-num text-foreground font-semibold">
              {total}
            </span>{" "}
            contacts across{" "}
            <span className="zg-num text-foreground font-semibold">
              {companies}
            </span>{" "}
            companies
            {lastImport?.at ? (
              <>
                {" · imported "}
                {new Date(lastImport.at).toLocaleDateString(undefined, {
                  dateStyle: "medium",
                })}
              </>
            ) : null}
            .
          </p>
        ) : (
          <p className="text-muted-foreground text-sm">
            No contacts imported yet.
          </p>
        )}

        {/* Source toggle */}
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground text-xs">CSV from:</span>
          {(["linkedin", "google"] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSource(s)}
              className={
                "rounded-[var(--radius-chip)] border px-2.5 py-1 text-xs capitalize transition-colors " +
                (source === s
                  ? "border-primary text-primary bg-accent"
                  : "border-border text-muted-foreground hover:text-foreground")
              }
            >
              {s}
            </button>
          ))}
        </div>

        {/* Actions */}
        <div className="flex flex-wrap items-center gap-2">
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            onChange={onFile}
            className="hidden"
          />
          <Button size="sm" onClick={onPick} disabled={importMut.isPending}>
            {importMut.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Upload className="size-3.5" />
            )}
            Choose CSV
          </Button>
          {total > 0 && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setConfirmClear(true)}
              disabled={clearMut.isPending}
              className="text-muted-foreground hover:text-destructive"
            >
              <Trash2 className="size-3.5" />
              Clear
            </Button>
          )}
        </div>

        {/* Privacy note */}
        <p className="text-muted-foreground flex items-start gap-1.5 text-xs leading-relaxed">
          <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-[var(--zg-success)]" />
          Read on your computer and stored on this computer — your contacts are
          never uploaded.
        </p>

        {/* How-to */}
        <div className="border-border/60 bg-secondary/40 rounded-md border p-3">
          <div className="flex items-start justify-between gap-2">
            <p className="text-muted-foreground text-xs leading-relaxed">
              <span className="text-foreground font-medium">
                Export from LinkedIn:
              </span>{" "}
              {LINKEDIN_STEPS}
            </p>
            <Button
              size="icon"
              variant="ghost"
              aria-label="Copy the export steps"
              className="text-muted-foreground hover:text-foreground size-7 shrink-0"
              onClick={onCopySteps}
            >
              {copied ? (
                <Check className="size-3.5" />
              ) : (
                <Copy className="size-3.5" />
              )}
            </Button>
          </div>
        </div>
      </CardContent>

      <ConfirmDialog
        open={confirmClear}
        onOpenChange={setConfirmClear}
        title="Clear your imported network?"
        description="This removes every imported contact from this computer. You can re-import the CSV anytime."
        confirmLabel="Clear all"
        cancelLabel="Keep them"
        destructive
        onConfirm={onClear}
      />
    </Card>
  );
}
