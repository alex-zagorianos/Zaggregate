import * as React from "react";
import { toast } from "sonner";
import {
  PlugZap,
  ExternalLink,
  Eye,
  EyeOff,
  ClipboardPaste,
  Loader2,
  CheckCircle2,
  XCircle,
} from "lucide-react";

import {
  useSourceKeys,
  useSaveSourceKey,
  useTestSourceKey,
} from "@/api/queries";
import {
  endpoints,
  ApiError,
  type SourceKeyInfo,
  type SourceField,
} from "@/api/client";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/* Connect Job Sources — data-driven from GET /api/settings/keys. One card per
 * keyed source: impact line, a "Get a free key" deep link, a masked input per
 * credential field (with a reveal toggle), Save (PUT + toast), and Test (POST →
 * inline colored status dot + detail). Adzuna also gets a "Paste both from
 * clipboard" button that hits the split endpoint and fills both fields.
 *
 * Deliberate simplification (tk parity note): the tk dialog auto-runs a debounced
 * live test after a paste settles. Here Save + Test are explicit — no debounced
 * auto-test — which is calmer on the web and avoids surprise network calls. */

export function SourcesTab() {
  const query = useSourceKeys();
  const sources = query.data?.sources ?? [];

  return (
    <section aria-labelledby="sources-heading">
      <div className="space-y-1">
        <h1
          id="sources-heading"
          className="zg-serif text-foreground flex items-center gap-2.5 text-2xl font-semibold tracking-tight"
        >
          <PlugZap className="text-primary size-6" strokeWidth={2} />
          Connect Job Sources
        </h1>
        <p className="text-muted-foreground max-w-2xl text-sm leading-relaxed">
          Add a free key to widen the net. Each key stays on this computer, in
          your data folder — it is never uploaded, and this page only ever shows
          the last four characters.
        </p>
      </div>

      {query.isLoading ? (
        <div className="mt-8">
          <LoadingState />
        </div>
      ) : query.isError ? (
        <div className="mt-8">
          <ErrorState
            title="Couldn't load your sources"
            message={
              query.error instanceof ApiError
                ? query.error.message
                : "The settings service didn't respond."
            }
            onRetry={() => query.refetch()}
          />
        </div>
      ) : sources.length === 0 ? (
        <div className="mt-8">
          <EmptyState
            icon={PlugZap}
            title="No sources configured"
            message="No keyed sources are available yet."
          />
        </div>
      ) : (
        <div className="mt-8 grid gap-5 md:grid-cols-2">
          {sources.map((src) => (
            <SourceCard key={src.id} source={src} />
          ))}
        </div>
      )}
    </section>
  );
}

type TestState =
  | { status: "idle" }
  | { status: "testing" }
  | { status: "ok" | "failed"; detail: string };

function SourceCard({ source }: { source: SourceKeyInfo }) {
  const save = useSaveSourceKey();
  const test = useTestSourceKey();

  // Field editor state: the current input value per field. Empty string = leave
  // as-is on the server IF it was already set (we only send changed non-empty
  // fields on save, so a masked-but-untouched field is preserved). A field the
  // user clears to empty is sent as "" (explicit clear).
  const [values, setValues] = React.useState<Record<string, string>>(() =>
    Object.fromEntries(source.fields.map((f) => [f.name, ""])),
  );
  const [reveal, setReveal] = React.useState<Record<string, boolean>>({});
  const [testState, setTestState] = React.useState<TestState>({
    status: "idle",
  });

  const setValue = (name: string, v: string) =>
    setValues((prev) => ({ ...prev, [name]: v }));

  const onSave = () => {
    // Send only fields the user actually typed into (non-empty), so an untouched
    // masked field isn't overwritten with blank. A field intentionally emptied
    // after typing is an edge we accept as "no change" here (clearing a key is a
    // rare action; the tk dialog is the escape hatch).
    const dirty = Object.fromEntries(
      Object.entries(values).filter(([, v]) => v.trim() !== ""),
    );
    if (Object.keys(dirty).length === 0) {
      toast("Nothing to save", {
        description: "Type a value into a field first.",
      });
      return;
    }
    save.mutate(
      { source: source.id, fields: dirty },
      {
        onSuccess: (res) => {
          const warned = res.warnings.length > 0;
          toast(warned ? "Saved (check the value)" : "Saved", {
            description: warned
              ? `${source.label}: a value looks unusually short — Test it to be sure.`
              : `${source.label} credentials saved.`,
          });
          // Clear the local inputs; the query refetch flips them to masked/set.
          setValues(Object.fromEntries(source.fields.map((f) => [f.name, ""])));
        },
        onError: (e) =>
          toast.error("Couldn't save", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          }),
      },
    );
  };

  const onTest = () => {
    setTestState({ status: "testing" });
    test.mutate(source.id, {
      onSuccess: (res) =>
        setTestState({ status: res.result.status, detail: res.result.detail }),
      onError: (e) =>
        setTestState({
          status: "failed",
          detail: e instanceof ApiError ? e.message : "Test failed.",
        }),
    });
  };

  const onPasteBoth = async () => {
    let clip = "";
    try {
      clip = await navigator.clipboard.readText();
    } catch {
      toast.error("Clipboard blocked", {
        description: "Allow clipboard access, or paste the fields manually.",
      });
      return;
    }
    try {
      const res = await endpoints.splitAdzuna(clip);
      if (res.ok) {
        if (res.app_id) setValue("adzuna_app_id", res.app_id);
        if (res.app_key) setValue("adzuna_app_key", res.app_key);
        setReveal((r) => ({
          ...r,
          adzuna_app_id: true,
          adzuna_app_key: true,
        }));
        toast.success("Pasted from clipboard", {
          description: "Review the fields, then Save.",
        });
      } else {
        toast.error("No Adzuna values found", {
          description:
            "Copy both from the Adzuna page, or paste them manually.",
        });
      }
    } catch (e) {
      toast.error("Couldn't read clipboard", {
        description: e instanceof ApiError ? e.message : "Please try again.",
      });
    }
  };

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <CardTitle>{source.label}</CardTitle>
          <SetBadge fields={source.fields} />
        </div>
        {source.impact && (
          <p className="text-muted-foreground text-sm leading-relaxed">
            {source.impact}
          </p>
        )}
        <a
          href={source.get_key_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary mt-0.5 inline-flex w-fit items-center gap-1 text-sm font-medium hover:underline"
        >
          Get a free key
          <ExternalLink className="size-3.5" />
        </a>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="space-y-3">
          {source.fields.map((f) => (
            <FieldRow
              key={f.name}
              field={f}
              value={values[f.name] ?? ""}
              reveal={!!reveal[f.name]}
              onChange={(v) => setValue(f.name, v)}
              onToggleReveal={() =>
                setReveal((r) => ({ ...r, [f.name]: !r[f.name] }))
              }
            />
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={onSave} disabled={save.isPending}>
            {save.isPending && <Loader2 className="size-3.5 animate-spin" />}
            Save
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onTest}
            disabled={testState.status === "testing"}
          >
            {testState.status === "testing" && (
              <Loader2 className="size-3.5 animate-spin" />
            )}
            Test
          </Button>
          {source.id === "adzuna" && (
            <Button size="sm" variant="ghost" onClick={onPasteBoth}>
              <ClipboardPaste className="size-3.5" />
              Paste both from clipboard
            </Button>
          )}
        </div>

        <TestResult state={testState} />
      </CardContent>
    </Card>
  );
}

function FieldRow({
  field,
  value,
  reveal,
  onChange,
  onToggleReveal,
}: {
  field: SourceField;
  value: string;
  reveal: boolean;
  onChange: (v: string) => void;
  onToggleReveal: () => void;
}) {
  const id = `field-${field.name}`;
  // Placeholder shows the masked last-4 for a field already set on the server, so
  // an untouched masked field reads "already saved" rather than looking empty.
  const placeholder = field.set
    ? (field.masked ?? "saved")
    : `Enter ${field.label.toLowerCase()}`;
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-muted-foreground text-xs">
        {field.label}
        {field.set && (
          <span className="text-[var(--zg-success)]/90 ml-1 text-[0.7rem] font-normal">
            · saved {field.masked}
          </span>
        )}
      </Label>
      <div className="relative">
        <Input
          id={id}
          type={reveal ? "text" : "password"}
          value={value}
          placeholder={placeholder}
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => onChange(e.target.value)}
          className="zg-num pr-9"
        />
        <button
          type="button"
          tabIndex={-1}
          onClick={onToggleReveal}
          aria-label={reveal ? "Hide value" : "Show value"}
          className="text-muted-foreground hover:text-foreground absolute top-1/2 right-2 -translate-y-1/2 rounded p-0.5 transition-colors"
        >
          {reveal ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
      </div>
    </div>
  );
}

/** A compact "connected / not set" badge summarizing the source's fields. */
function SetBadge({ fields }: { fields: SourceField[] }) {
  const setCount = fields.filter((f) => f.set).length;
  const all = setCount === fields.length;
  const some = setCount > 0;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-[var(--radius-chip)] border px-2 py-0.5 text-xs font-medium",
        all
          ? "border-[var(--zg-success)]/40 bg-[var(--zg-success)]/12 text-[var(--zg-success)]"
          : some
            ? "border-[var(--zg-warn)]/40 bg-[var(--zg-warn)]/12 text-[var(--zg-warn)]"
            : "border-border text-muted-foreground",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "size-1.5 rounded-full",
          all
            ? "bg-[var(--zg-success)]"
            : some
              ? "bg-[var(--zg-warn)]"
              : "bg-muted-foreground/50",
        )}
      />
      {all ? "Connected" : some ? "Partial" : "Not set"}
    </span>
  );
}

function TestResult({ state }: { state: TestState }) {
  if (state.status === "idle") return null;
  if (state.status === "testing") {
    return (
      <p className="text-muted-foreground flex items-center gap-2 text-sm">
        <Loader2 className="size-4 animate-spin" />
        Testing your key…
      </p>
    );
  }
  const ok = state.status === "ok";
  return (
    <p
      className={cn(
        "flex items-start gap-2 text-sm leading-relaxed",
        ok ? "text-[var(--zg-success)]" : "text-destructive",
      )}
    >
      {ok ? (
        <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
      ) : (
        <XCircle className="mt-0.5 size-4 shrink-0" />
      )}
      <span>
        {ok ? "Working — " : "Not working — "}
        <span className="text-muted-foreground">{state.detail}</span>
      </span>
    </p>
  );
}
