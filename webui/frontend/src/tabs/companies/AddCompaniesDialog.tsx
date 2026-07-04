import * as React from "react";
import { toast } from "sonner";
import {
  Loader2,
  Building2,
  ArrowRight,
  CheckCircle2,
  XCircle,
  Link2,
  MinusCircle,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  endpoints,
  validateResult,
  ApiError,
  type JobStatus,
  type RunConflictBody,
} from "@/api/client";
import {
  rowsFromCandidates,
  markValidating,
  applyVerdicts,
  reconcileUnverdicted,
  validatableCandidates,
  addEntries,
  addSummary,
  type DetectRow,
  type RowPhase,
} from "@/lib/detect-table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { JobLogConsole } from "@/components/job-log-console";
import { cn } from "@/lib/utils";

/* Add Companies — the tk "Add Companies" dialog, on the web.
 *
 * Flow: paste `Name | careers-URL` lines → Detect (instant, per-line ATS parse) →
 * a table of candidates → Validate (a background job live-probes each board,
 * streaming a log; verdicts stream back) → per-row verdict chips → Add (with a
 * keep-unreachable confirm, P0-6 verified-by-default gating server-side).
 *
 * INCLUSION OVER PRECISION: dropped lines (no URL) are shown, not eaten; the user
 * decides whether to keep unreachable boards. */

type Phase = "input" | "table";

export function AddCompaniesDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const qc = useQueryClient();
  const [phase, setPhase] = React.useState<Phase>("input");
  const [raw, setRaw] = React.useState("");
  const [industry, setIndustry] = React.useState("");
  const [rows, setRows] = React.useState<DetectRow[]>([]);
  const [detecting, setDetecting] = React.useState(false);

  // Validate job
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [validating, setValidating] = React.useState(false);

  // Add
  const [keepUnreachable, setKeepUnreachable] = React.useState(false);
  const [confirmAdd, setConfirmAdd] = React.useState(false);
  const [adding, setAdding] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    setPhase("input");
    setRaw("");
    setIndustry("");
    setRows([]);
    setJobId(null);
    setValidating(false);
    setKeepUnreachable(false);
    setAdding(false);
  }, [open]);

  const onDetect = () => {
    if (!raw.trim()) return;
    setDetecting(true);
    endpoints
      .detectCompanies(raw)
      .then((r) => {
        const mapped = rowsFromCandidates(r.candidates);
        setRows(mapped);
        setPhase("table");
        if (mapped.length === 0)
          toast("Nothing detected", {
            description: "No companies found. Paste Name | careers-URL lines.",
          });
      })
      .catch((e) =>
        toast.error("Couldn't detect", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
      )
      .finally(() => setDetecting(false));
  };

  const onValidate = () => {
    const cands = validatableCandidates(rows);
    if (cands.length === 0) {
      toast("Nothing to validate", {
        description: "Every line is a direct careers page or was dropped.",
      });
      return;
    }
    setValidating(true);
    setRows((prev) => markValidating(prev));
    endpoints
      .validateCompanies(cands)
      .then((r) => setJobId(r.job_id))
      .catch((e) => {
        setValidating(false);
        setRows((prev) => reconcileUnverdicted(prev));
        if (e instanceof ApiError && e.status === 409) {
          const body = e.body as RunConflictBody | null;
          if (body?.job_id) {
            setJobId(body.job_id);
            setValidating(true);
            return;
          }
        }
        toast.error("Couldn't start validation", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        });
      });
  };

  const onValidateResult = React.useCallback(
    (_result: unknown, _status: JobStatus) => {
      // Prefer the typed snapshot fetch (the generic result is `unknown`).
      if (!jobId) return;
      validateResult(jobId)
        .then((snap) => {
          const verdicts = snap.result?.results ?? [];
          setRows((prev) =>
            reconcileUnverdicted(applyVerdicts(prev, verdicts)),
          );
        })
        .catch(() => setRows((prev) => reconcileUnverdicted(prev)));
    },
    [jobId],
  );

  const onValidateTerminal = React.useCallback((_status: JobStatus) => {
    setValidating(false);
  }, []);

  const summary = addSummary(rows, keepUnreachable);

  const doAdd = () => {
    const entries = addEntries(rows, industry);
    if (entries.length === 0) {
      toast("Nothing to add", {
        description: "No usable companies in the list.",
      });
      return;
    }
    setAdding(true);
    endpoints
      .addCompanies(entries, keepUnreachable)
      .then((r) => {
        toast.success("Companies added", {
          description: `${r.added} added (${r.verified} verified${r.unverified ? `, ${r.unverified} unverified` : ""}${r.rejected ? `, ${r.rejected} rejected` : ""}).`,
        });
        // The registry changed — the next daily run / build picks it up. Nothing
        // cached to invalidate directly, but refresh inbox badges defensively.
        qc.invalidateQueries({ queryKey: ["inbox"] });
        onOpenChange(false);
      })
      .catch((e) =>
        toast.error("Couldn't add companies", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
      )
      .finally(() => setAdding(false));
  };

  const onAddClick = () => {
    if (summary.unreachable > 0 && !keepUnreachable) {
      // Offer to keep them, but the primary path is add-verified-only.
      setConfirmAdd(true);
    } else {
      doAdd();
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="zg-serif flex items-center gap-2">
            <Building2 className="text-primary size-5" />
            Add companies
          </DialogTitle>
          <DialogDescription>
            Paste employers as{" "}
            <span className="zg-num">Name | careers-URL</span> (one per line).
            We detect the job board, verify it's live, and add the good ones to
            your target list.
          </DialogDescription>
        </DialogHeader>

        {phase === "input" ? (
          <>
            <Textarea
              value={raw}
              onChange={(e) => setRaw(e.target.value)}
              placeholder={
                "Acme Robotics | https://boards.greenhouse.io/acme\nGlobex | https://globex.com/careers"
              }
              rows={8}
              className="zg-num text-xs"
              autoFocus
            />
            <div className="flex items-end justify-between gap-3">
              <div className="w-56 space-y-1.5">
                <Label
                  htmlFor="add-industry"
                  className="text-muted-foreground text-xs"
                >
                  Tag with field (optional)
                </Label>
                <Input
                  id="add-industry"
                  value={industry}
                  onChange={(e) => setIndustry(e.target.value)}
                  placeholder="e.g. mechanical engineering"
                  autoComplete="off"
                />
              </div>
              <Button onClick={onDetect} disabled={detecting || !raw.trim()}>
                {detecting ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <ArrowRight className="size-4" />
                )}
                Detect
              </Button>
            </div>
          </>
        ) : (
          <>
            <DetectTable rows={rows} />

            {jobId && (
              <JobLogConsole
                jobId={jobId}
                title="Verifying boards"
                onResult={onValidateResult}
                onTerminal={onValidateTerminal}
              />
            )}

            <div className="flex flex-wrap items-center justify-between gap-3">
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={keepUnreachable}
                  onChange={(e) => setKeepUnreachable(e.target.checked)}
                  className="accent-[var(--zg-accent)]"
                />
                <span className="text-foreground">
                  Keep unreachable boards
                  <span className="text-muted-foreground">
                    {" "}
                    (saved but not scraped until they verify)
                  </span>
                </span>
              </label>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setPhase("input")}
                >
                  Back
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onValidate}
                  disabled={validating}
                >
                  {validating && <Loader2 className="size-3.5 animate-spin" />}
                  {rows.some(
                    (r) => r.phase === "live" || r.phase === "unreachable",
                  )
                    ? "Re-verify"
                    : "Verify boards"}
                </Button>
                <Button
                  size="sm"
                  onClick={onAddClick}
                  disabled={
                    adding || summary.willAdd + summary.unreachable === 0
                  }
                >
                  {adding && <Loader2 className="size-3.5 animate-spin" />}
                  Add{" "}
                  {summary.willAdd > 0 ? summary.willAdd : summary.unreachable}
                </Button>
              </div>
            </div>
          </>
        )}
      </DialogContent>

      <ConfirmDialog
        open={confirmAdd}
        onOpenChange={setConfirmAdd}
        title="Keep the unreachable boards too?"
        description={`${summary.unreachable} board${summary.unreachable === 1 ? "" : "s"} couldn't be reached. Add just the ${summary.live} verified, or keep the unreachable ones too (they'll be saved but skipped until they verify).`}
        confirmLabel="Add verified only"
        cancelLabel="Cancel"
        onConfirm={doAdd}
      />
    </Dialog>
  );
}

// ── the detect table ──────────────────────────────────────────────────────────

function DetectTable({ rows }: { rows: DetectRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="text-muted-foreground py-6 text-center text-sm">
        No companies detected.
      </p>
    );
  }
  return (
    <div className="border-border bg-card max-h-64 overflow-auto rounded-md border">
      <table className="w-full text-sm">
        <thead className="bg-secondary/40 sticky top-0">
          <tr className="border-border/70 border-b">
            <th className="text-muted-foreground px-3 py-2 text-left text-xs font-semibold tracking-wide uppercase">
              Company
            </th>
            <th className="text-muted-foreground hidden px-3 py-2 text-left text-xs font-semibold tracking-wide uppercase sm:table-cell">
              Board
            </th>
            <th className="text-muted-foreground px-3 py-2 text-right text-xs font-semibold tracking-wide uppercase">
              Status
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={`${r.line}-${i}`}
              className={cn(
                "border-border/60 border-b last:border-0",
                r.phase === "dropped" && "opacity-55",
              )}
            >
              <td className="px-3 py-2 align-middle">
                <div className="flex min-w-0 flex-col">
                  <span className="text-foreground truncate font-medium">
                    {r.name || (r.phase === "dropped" ? r.line : "Unnamed")}
                  </span>
                  {r.detail && (
                    <span className="text-muted-foreground truncate text-xs">
                      {r.detail}
                    </span>
                  )}
                </div>
              </td>
              <td className="text-muted-foreground hidden px-3 py-2 align-middle text-xs capitalize sm:table-cell">
                {r.ats || "—"}
              </td>
              <td className="px-3 py-2 text-right align-middle">
                <VerdictChip phase={r.phase} count={r.count} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function VerdictChip({ phase, count }: { phase: RowPhase; count?: number }) {
  const map: Record<
    RowPhase,
    { label: string; cls: string; icon: React.ReactNode }
  > = {
    detected: {
      label: "detected",
      cls: "border-border text-muted-foreground",
      icon: <Link2 className="size-3" />,
    },
    validating: {
      label: "checking…",
      cls: "border-primary/40 text-primary bg-primary/10",
      icon: <Loader2 className="size-3 animate-spin" />,
    },
    live: {
      label: count != null ? `live · ${count}` : "live",
      cls: "border-[var(--zg-success)]/40 text-[var(--zg-success)] bg-[var(--zg-success)]/12",
      icon: <CheckCircle2 className="size-3" />,
    },
    direct: {
      label: "direct page",
      cls: "border-[var(--zg-success)]/40 text-[var(--zg-success)] bg-[var(--zg-success)]/10",
      icon: <CheckCircle2 className="size-3" />,
    },
    unreachable: {
      label: "unreachable",
      cls: "border-destructive/40 text-destructive bg-destructive/10",
      icon: <XCircle className="size-3" />,
    },
    dropped: {
      label: "no URL",
      cls: "border-border text-muted-foreground",
      icon: <MinusCircle className="size-3" />,
    },
  };
  const s = map[phase];
  return (
    <span
      className={cn(
        "zg-num inline-flex items-center gap-1 rounded-[var(--radius-chip)] border px-1.5 py-0.5 text-[0.7rem] font-medium whitespace-nowrap",
        s.cls,
      )}
    >
      {s.icon}
      {s.label}
    </span>
  );
}
