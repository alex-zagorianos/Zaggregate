import * as React from "react";
import { toast } from "sonner";
import { Loader2, ListPlus, Play } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  endpoints,
  ApiError,
  type JobStatus,
  type BuildListOpts,
  type RunConflictBody,
} from "@/api/client";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { JobLogConsole } from "@/components/job-log-console";

/* Build My List — grow the target-company list for the active project. Options
 * form (metro/industry override + toggles) → an EXCLUSIVE engine job whose log
 * streams into the JobLogConsole → a summary line on finish. Mirrors the tk
 * "Build My List" dialog + the CLI flags.
 *
 * All fields are optional: blank metro/industry fall back to the project config
 * server-side. The engine touches the registry + engine globals, so it runs on
 * the shared single-flight mutex (409 → the running job's log is shown instead of
 * a duplicate). */

export function BuildListDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const qc = useQueryClient();
  const [metro, setMetro] = React.useState("");
  const [industry, setIndustry] = React.useState("");
  const [useInbox, setUseInbox] = React.useState(true);
  const [seedMetro, setSeedMetro] = React.useState(false);
  const [national, setNational] = React.useState(false);
  const [classify, setClassify] = React.useState(false);

  const [jobId, setJobId] = React.useState<string | null>(null);
  const [running, setRunning] = React.useState(false);
  const [done, setDone] = React.useState<JobStatus | null>(null);

  React.useEffect(() => {
    if (!open) return;
    setMetro("");
    setIndustry("");
    setUseInbox(true);
    setSeedMetro(false);
    setNational(false);
    setClassify(false);
    setJobId(null);
    setRunning(false);
    setDone(null);
  }, [open]);

  const start = () => {
    const opts: BuildListOpts = {
      metro: metro.trim() || undefined,
      industry: industry.trim() || undefined,
      use_inbox: useInbox,
      seed_metro: seedMetro,
      national,
      classify,
    };
    setRunning(true);
    setDone(null);
    endpoints
      .buildCompanyList(opts)
      .then((r) => setJobId(r.job_id))
      .catch((e) => {
        setRunning(false);
        if (e instanceof ApiError && e.status === 409) {
          const body = e.body as RunConflictBody | null;
          if (body?.job_id) {
            setJobId(body.job_id);
            setRunning(true);
            toast("A build is already running", {
              description: "Showing its progress below.",
            });
            return;
          }
        }
        toast.error("Couldn't start the build", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        });
      });
  };

  const onTerminal = React.useCallback(
    (status: JobStatus) => {
      setRunning(false);
      setDone(status);
      if (status === "done") {
        toast.success("List built", {
          description: "Your target-company list has been updated.",
        });
        qc.invalidateQueries({ queryKey: ["inbox"] });
      } else if (status === "failed") {
        toast.error("Build failed", {
          description: "See the log for details.",
        });
      }
    },
    [qc],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="zg-serif flex items-center gap-2">
            <ListPlus className="text-primary size-5" />
            Build my company list
          </DialogTitle>
          <DialogDescription>
            Grow your target-employer list from your inbox, public datasets, and
            local seeding. Leave the fields blank to use your project's field
            and location.
          </DialogDescription>
        </DialogHeader>

        {!jobId ? (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label
                  htmlFor="build-metro"
                  className="text-muted-foreground text-xs"
                >
                  Metro (optional)
                </Label>
                <Input
                  id="build-metro"
                  value={metro}
                  onChange={(e) => setMetro(e.target.value)}
                  placeholder="e.g. Cincinnati, OH"
                  autoComplete="off"
                />
              </div>
              <div className="space-y-1.5">
                <Label
                  htmlFor="build-industry"
                  className="text-muted-foreground text-xs"
                >
                  Field (optional)
                </Label>
                <Input
                  id="build-industry"
                  value={industry}
                  onChange={(e) => setIndustry(e.target.value)}
                  placeholder="e.g. mechanical engineering"
                  autoComplete="off"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              <Toggle
                checked={useInbox}
                onChange={setUseInbox}
                label="Mine my inbox for employers"
              />
              <Toggle
                checked={seedMetro}
                onChange={setSeedMetro}
                label="Seed local employers"
              />
              <Toggle
                checked={national}
                onChange={setNational}
                label="Include national employers"
              />
              <Toggle
                checked={classify}
                onChange={setClassify}
                label="Classify by field (slower)"
              />
            </div>

            <div className="flex justify-end">
              <Button onClick={start} disabled={running}>
                {running ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Play className="size-4" />
                )}
                Build list
              </Button>
            </div>
          </>
        ) : (
          <>
            <JobLogConsole
              jobId={jobId}
              title="Building your list"
              onTerminal={onTerminal}
            />
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => onOpenChange(false)}
                disabled={running}
              >
                {done ? "Close" : "Run in background"}
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-[var(--zg-accent)]"
      />
      <span className="text-foreground">{label}</span>
    </label>
  );
}
