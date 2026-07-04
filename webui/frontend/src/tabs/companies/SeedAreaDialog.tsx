import * as React from "react";
import { toast } from "sonner";
import {
  Loader2,
  MapPin,
  Play,
  KeyRound,
  Sparkles,
  Copy,
  Check,
  PlugZap,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  endpoints,
  ApiError,
  type JobStatus,
  type SeedMetroArgs,
  type SeedKeyConflictBody,
  type SeedApplyResult,
  type RunConflictBody,
} from "@/api/client";
import { copyText } from "@/lib/clipboard";
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
import { Textarea } from "@/components/ui/textarea";
import { JobLogConsole } from "@/components/job-log-console";
import { cn } from "@/lib/utils";

/* Seed My Area — seed a VERIFIED local-employer registry.
 *
 * Two lanes:
 *   • Direct (CareerOneStop) — KEY-GATED: a keyless run returns 409 {need_key},
 *     so this lane shows a "connect a key" state linking to Sources. With a key,
 *     the form starts an exclusive engine job whose log streams live.
 *   • AI seed — copy a prompt asking your AI for `Name | careers-URL` lines,
 *     paste the reply, apply synchronously (detect+probe+save, P0-6 gated). This
 *     lane needs no key, so it's always available.
 *
 * The dialog opens on the AI lane by default (always usable) with the direct lane
 * a click away; the direct lane self-heals from keyless → form once a key is set. */

type Lane = "ai" | "direct";

export function SeedAreaDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [lane, setLane] = React.useState<Lane>("ai");

  React.useEffect(() => {
    if (open) setLane("ai");
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="zg-serif flex items-center gap-2">
            <MapPin className="text-primary size-5" />
            Seed my area
          </DialogTitle>
          <DialogDescription>
            Add local employers to your target list. Use your own AI (no key
            needed) or pull verified employers straight from CareerOneStop.
          </DialogDescription>
        </DialogHeader>

        <div className="border-border bg-secondary/40 inline-flex w-fit rounded-md border p-0.5 text-sm">
          <LaneTab active={lane === "ai"} onClick={() => setLane("ai")}>
            <Sparkles className="size-3.5" />
            With my AI
          </LaneTab>
          <LaneTab active={lane === "direct"} onClick={() => setLane("direct")}>
            <KeyRound className="size-3.5" />
            CareerOneStop
          </LaneTab>
        </div>

        {lane === "ai" ? (
          <AiSeedLane onClose={() => onOpenChange(false)} />
        ) : (
          <DirectSeedLane onClose={() => onOpenChange(false)} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function LaneTab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[5px] px-3 py-1.5 font-medium transition-colors",
        active
          ? "bg-card text-foreground shadow-xs"
          : "text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

// ── AI seed lane (no key) ─────────────────────────────────────────────────────

function AiSeedLane({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [field, setField] = React.useState("");
  const [metro, setMetro] = React.useState("");
  const [prompt, setPrompt] = React.useState("");
  const [loadingPrompt, setLoadingPrompt] = React.useState(false);
  const [copied, setCopied] = React.useState(false);
  const [reply, setReply] = React.useState("");
  const [applying, setApplying] = React.useState(false);
  const [result, setResult] = React.useState<SeedApplyResult | null>(null);

  const getPrompt = () => {
    setLoadingPrompt(true);
    endpoints
      .seedPrompt({ field: field.trim(), metro: metro.trim(), limit: 30 })
      .then((r) => setPrompt(r.prompt))
      .catch((e) =>
        toast.error("Couldn't build the prompt", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
      )
      .finally(() => setLoadingPrompt(false));
  };

  const onCopy = async () => {
    const ok = await copyText(prompt);
    if (ok) {
      setCopied(true);
      toast.success("Prompt copied", {
        description: "Paste it into your AI, then paste its reply back here.",
      });
      window.setTimeout(() => setCopied(false), 1600);
    } else {
      toast.error("Couldn't copy", { description: "Copy it manually." });
    }
  };

  const onApply = () => {
    if (!reply.trim()) return;
    setApplying(true);
    endpoints
      .seedApply(reply, field.trim() || undefined)
      .then((r) => {
        setResult(r.result);
        toast.success("Employers seeded", {
          description: `${r.result.added} added (${r.result.verified} verified).`,
        });
        qc.invalidateQueries({ queryKey: ["inbox"] });
      })
      .catch((e) =>
        toast.error("Couldn't apply", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
      )
      .finally(() => setApplying(false));
  };

  if (result) {
    return <SeedResultView result={result} onClose={onClose} />;
  }

  return (
    <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="seed-field" className="text-muted-foreground text-xs">
            Field (optional)
          </Label>
          <Input
            id="seed-field"
            value={field}
            onChange={(e) => setField(e.target.value)}
            placeholder="e.g. nursing"
            autoComplete="off"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="seed-metro" className="text-muted-foreground text-xs">
            Metro (optional)
          </Label>
          <Input
            id="seed-metro"
            value={metro}
            onChange={(e) => setMetro(e.target.value)}
            placeholder="e.g. Cincinnati, OH"
            autoComplete="off"
          />
        </div>
      </div>

      {!prompt ? (
        <div className="flex justify-end">
          <Button onClick={getPrompt} disabled={loadingPrompt}>
            {loadingPrompt ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Sparkles className="size-4" />
            )}
            Build the prompt
          </Button>
        </div>
      ) : (
        <>
          <div className="space-y-1.5">
            <Label className="text-muted-foreground text-xs">
              1 · Copy this into your AI
            </Label>
            <Textarea
              value={prompt}
              readOnly
              rows={6}
              className="text-xs"
              onFocus={(e) => e.currentTarget.select()}
            />
            <div className="flex justify-end">
              <Button variant="outline" size="sm" onClick={onCopy}>
                {copied ? (
                  <Check className="size-4" />
                ) : (
                  <Copy className="size-4" />
                )}
                {copied ? "Copied" : "Copy prompt"}
              </Button>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label
              htmlFor="seed-reply"
              className="text-muted-foreground text-xs"
            >
              2 · Paste the AI's reply
            </Label>
            <Textarea
              id="seed-reply"
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              placeholder={"Company Name | https://careers-page-url\n…"}
              rows={5}
              className="zg-num text-xs"
            />
          </div>
          <div className="flex justify-end">
            <Button onClick={onApply} disabled={applying || !reply.trim()}>
              {applying && <Loader2 className="size-3.5 animate-spin" />}
              Add these employers
            </Button>
          </div>
        </>
      )}
    </>
  );
}

function SeedResultView({
  result,
  onClose,
}: {
  result: SeedApplyResult;
  onClose: () => void;
}) {
  const stats: { label: string; value: number; tone?: string }[] = [
    { label: "Added", value: result.added, tone: "text-[var(--zg-success)]" },
    { label: "Verified", value: result.verified },
    { label: "Unverified", value: result.unverified },
    { label: "Skipped", value: result.skipped },
    { label: "Rejected", value: result.rejected, tone: "text-destructive" },
  ];
  return (
    <>
      <div className="border-[var(--zg-success)]/30 bg-[var(--zg-success)]/8 grid grid-cols-3 gap-3 rounded-md border p-3 sm:grid-cols-5">
        {stats.map((s) => (
          <div key={s.label} className="text-center">
            <div
              className={cn(
                "zg-num text-xl font-semibold",
                s.tone ?? "text-foreground",
              )}
            >
              {s.value}
            </div>
            <div className="text-muted-foreground text-xs">{s.label}</div>
          </div>
        ))}
      </div>
      {result.verdicts.length > 0 && (
        <div className="border-border max-h-48 overflow-auto rounded-md border">
          <ul className="divide-border divide-y text-sm">
            {result.verdicts.map((v, i) => (
              <li
                key={`${v.slug}-${i}`}
                className="flex items-center justify-between gap-3 px-3 py-1.5"
              >
                <span className="text-foreground truncate">
                  {v.name || v.slug}
                </span>
                <span className="text-muted-foreground shrink-0 text-xs">
                  {v.detail}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex justify-end">
        <Button size="sm" onClick={onClose}>
          Done
        </Button>
      </div>
    </>
  );
}

// ── Direct (CareerOneStop, key-gated) lane ────────────────────────────────────

function DirectSeedLane({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [field, setField] = React.useState("");
  const [metro, setMetro] = React.useState("");
  const [keyword, setKeyword] = React.useState("");
  const [needKey, setNeedKey] = React.useState(false);
  const [keyMsg, setKeyMsg] = React.useState("");
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [running, setRunning] = React.useState(false);
  const [done, setDone] = React.useState<JobStatus | null>(null);

  const start = () => {
    const args: SeedMetroArgs = {
      industry: field.trim() || undefined,
      metro: metro.trim() || undefined,
      keyword: keyword.trim() || undefined,
    };
    setRunning(true);
    setDone(null);
    setNeedKey(false);
    endpoints
      .seedMetro(args)
      .then((r) => setJobId(r.job_id))
      .catch((e) => {
        setRunning(false);
        if (e instanceof ApiError && e.status === 409) {
          const body = e.body as (SeedKeyConflictBody | RunConflictBody) | null;
          if (body && "need_key" in body && body.need_key) {
            setNeedKey(true);
            setKeyMsg(body.error);
            return;
          }
          if (body && "job_id" in body && body.job_id) {
            setJobId(body.job_id);
            setRunning(true);
            toast("A seed is already running", {
              description: "Showing its progress below.",
            });
            return;
          }
        }
        toast.error("Couldn't start seeding", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        });
      });
  };

  const onTerminal = React.useCallback(
    (status: JobStatus) => {
      setRunning(false);
      setDone(status);
      if (status === "done") {
        toast.success("Area seeded", {
          description: "Local employers added to your target list.",
        });
        qc.invalidateQueries({ queryKey: ["inbox"] });
      }
    },
    [qc],
  );

  if (needKey) {
    return (
      <div className="border-[var(--zg-warn)]/30 bg-[var(--zg-warn)]/8 flex flex-col items-start gap-3 rounded-md border p-4">
        <div className="flex items-center gap-2">
          <KeyRound className="size-5 text-[var(--zg-warn)]" />
          <h3 className="zg-serif text-foreground text-base font-semibold">
            A free CareerOneStop key is needed
          </h3>
        </div>
        <p className="text-muted-foreground text-sm leading-relaxed">
          {keyMsg}
        </p>
        <p className="text-muted-foreground text-sm leading-relaxed">
          No key handy? The{" "}
          <strong className="text-foreground">With my AI</strong> tab seeds your
          area with no key at all.
        </p>
        <Button size="sm" onClick={() => navigate("/sources")}>
          <PlugZap className="size-4" />
          Connect a key
        </Button>
      </div>
    );
  }

  if (jobId) {
    return (
      <>
        <JobLogConsole
          jobId={jobId}
          title="Seeding your area"
          onTerminal={onTerminal}
        />
        <div className="flex justify-end">
          <Button
            variant="outline"
            size="sm"
            onClick={onClose}
            disabled={running}
          >
            {done ? "Close" : "Run in background"}
          </Button>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label
            htmlFor="dseed-field"
            className="text-muted-foreground text-xs"
          >
            Field
          </Label>
          <Input
            id="dseed-field"
            value={field}
            onChange={(e) => setField(e.target.value)}
            placeholder="optional"
            autoComplete="off"
          />
        </div>
        <div className="space-y-1.5">
          <Label
            htmlFor="dseed-metro"
            className="text-muted-foreground text-xs"
          >
            Metro
          </Label>
          <Input
            id="dseed-metro"
            value={metro}
            onChange={(e) => setMetro(e.target.value)}
            placeholder="optional"
            autoComplete="off"
          />
        </div>
        <div className="space-y-1.5">
          <Label
            htmlFor="dseed-keyword"
            className="text-muted-foreground text-xs"
          >
            Keyword
          </Label>
          <Input
            id="dseed-keyword"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="optional"
            autoComplete="off"
          />
        </div>
      </div>
      <p className="text-muted-foreground text-xs leading-relaxed">
        Leave blank to use your project's field and location. Pulls verified
        employers from CareerOneStop's Business Finder.
      </p>
      <div className="flex justify-end">
        <Button onClick={start} disabled={running}>
          {running ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Play className="size-4" />
          )}
          Seed my area
        </Button>
      </div>
    </>
  );
}
