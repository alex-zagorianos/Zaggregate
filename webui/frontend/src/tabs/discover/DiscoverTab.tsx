import * as React from "react";
import { toast } from "sonner";
import {
  Compass,
  Sparkles,
  Loader2,
  Plus,
  Check,
  X,
  Search,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  useRecommend,
  useRecommendReply,
  useRecommendApply,
  useRecommendDismiss,
} from "@/api/queries";
import { endpoints, type Recommendation } from "@/api/client";
import { friendlyError } from "@/lib/friendly-error";
import { PromptDialog } from "@/components/prompt-dialog";
import { PasteDialog } from "@/components/paste-dialog";
import { EmptyState, TableSkeleton, useQueryGuard } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScoreChip } from "@/components/score-chip";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

/* Discover — EXPERIMENTAL (S36c). BYO-AI career-direction recommendations:
 * build a prompt from your experience + preferences + tracked-job signal, run
 * it through YOUR AI (no API key), paste the reply back, and get actionable
 * role cards — each can push its search keywords into your project config
 * (additive only) or fire a search right away. Web-only, isolated for easy
 * removal (see recommend.py). */

const LANES: { key: Recommendation["lane"]; label: string; hint: string }[] = [
  { key: "core", label: "Ready today", hint: "You could apply now" },
  { key: "adjacent", label: "Strong overlap", hint: "Small gap to close" },
  {
    key: "stretch",
    label: "Worth stretching for",
    hint: "Aspirational, reachable",
  },
];

export function DiscoverTab() {
  const query = useRecommend();
  const replyMut = useRecommendReply();
  const applyMut = useRecommendApply();
  const dismissMut = useRecommendDismiss();
  const navigate = useNavigate();

  const guard = useQueryGuard(query, {
    fallback: "",
    loading: <TableSkeleton rows={4} />,
  });

  const [interests, setInterests] = React.useState<string | null>(null);
  const [prompt, setPrompt] = React.useState("");
  const [promptOpen, setPromptOpen] = React.useState(false);
  const [pasteOpen, setPasteOpen] = React.useState(false);
  const [building, setBuilding] = React.useState(false);

  const state = query.data;
  // Seed the interests box from the saved note once (then it's user-owned).
  const interestsValue = interests ?? state?.interests ?? "";
  const recs = (state?.recommendations ?? []).filter((r) => !r.dismissed);

  const buildPrompt = React.useCallback(() => {
    setBuilding(true);
    endpoints
      .recommendPrompt(interestsValue.trim())
      .then((r) => {
        setPrompt(r.prompt);
        setPromptOpen(true);
      })
      .catch((e) =>
        toast.error("Couldn't build the prompt", {
          description: friendlyError(e),
        }),
      )
      .finally(() => setBuilding(false));
  }, [interestsValue]);

  const onPaste = React.useCallback(
    (text: string) => {
      replyMut.mutate(text, {
        onSuccess: (r) => {
          setPasteOpen(false);
          toast.success("Recommendations ready", {
            description: `${r.recommendations.length} directions to explore.`,
          });
        },
        onError: (e) =>
          toast.error("Couldn't read that reply", {
            description: friendlyError(e),
          }),
      });
    },
    [replyMut],
  );

  const onApply = React.useCallback(
    (rec: Recommendation) => {
      applyMut.mutate(rec.id, {
        onSuccess: (r) =>
          toast.success(
            r.added.length
              ? `Added ${r.added.length} keyword${r.added.length === 1 ? "" : "s"}`
              : "Already covered",
            {
              description: r.added.length
                ? `${r.added.join(", ")} — your next run will search these.`
                : "All of this card's keywords were in your search already.",
            },
          ),
        onError: (e) =>
          toast.error("Couldn't add keywords", {
            description: friendlyError(e),
          }),
      });
    },
    [applyMut],
  );

  const onSearchNow = React.useCallback(
    (rec: Recommendation) => {
      // Hand the keywords to the Search tab via sessionStorage prefill (the
      // lightest cross-tab handoff; Search reads/clears it on mount).
      try {
        sessionStorage.setItem("zg-search-prefill", rec.keywords.join(", "));
      } catch {
        /* best-effort */
      }
      navigate("/search");
    },
    [navigate],
  );

  return (
    <section aria-labelledby="discover-heading" className="flex flex-col">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1
            id="discover-heading"
            className="zg-serif text-foreground flex items-center gap-2.5 text-2xl font-semibold tracking-tight"
          >
            <Compass className="text-primary size-6" strokeWidth={2} />
            Discover
            <Badge variant="outline" className="text-muted-foreground ml-1">
              Experimental
            </Badge>
          </h1>
          <p className="text-muted-foreground max-w-2xl text-sm leading-relaxed">
            Ask your own AI where your experience could take you. It reads your
            resume, preferences, and the jobs you&apos;ve pursued — then
            suggests directions worth searching, which you can add to your
            search in one click.
          </p>
        </div>
        {state?.generated_at && (
          <span className="text-muted-foreground text-xs">
            Last generated{" "}
            {new Date(state.generated_at).toLocaleString(undefined, {
              dateStyle: "medium",
              timeStyle: "short",
            })}
          </span>
        )}
      </div>

      {/* Step strip: interests → prompt → paste */}
      <div className="border-border/60 bg-card/50 mt-5 rounded-lg border p-4">
        <label
          htmlFor="discover-interests"
          className="text-foreground text-sm font-medium"
        >
          What&apos;s interesting you lately?{" "}
          <span className="text-muted-foreground font-normal">
            (optional — steers the recommendations)
          </span>
        </label>
        <Textarea
          id="discover-interests"
          value={interestsValue}
          onChange={(e) => setInterests(e.target.value)}
          placeholder="e.g. humanoid robotics, AI-assisted engineering tools, medical devices…"
          rows={2}
          className="mt-2 text-sm"
        />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button onClick={buildPrompt} disabled={building}>
            {building ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Sparkles className="size-4" />
            )}
            Build my prompt
          </Button>
          <Button
            variant="outline"
            onClick={() => setPasteOpen(true)}
            disabled={replyMut.isPending}
          >
            Paste AI reply
          </Button>
          <span className="text-muted-foreground text-xs">
            Copy the prompt into Claude, ChatGPT, or any AI — then paste its
            answer back.
          </span>
        </div>
      </div>

      {/* Results */}
      {guard ? (
        <div className="mt-6">{guard}</div>
      ) : recs.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            icon={Compass}
            title="No recommendations yet"
            message="Build the prompt above, run it through your AI, and paste the reply — your personalized directions land here."
          />
        </div>
      ) : (
        <div className="mt-6 space-y-8">
          {LANES.map((lane) => {
            const cards = recs.filter((r) => r.lane === lane.key);
            if (cards.length === 0) return null;
            return (
              <div key={lane.key}>
                <div className="mb-3 flex items-baseline gap-2">
                  <h2 className="zg-serif text-foreground text-lg font-semibold">
                    {lane.label}
                  </h2>
                  <span className="text-muted-foreground text-xs">
                    {lane.hint}
                  </span>
                </div>
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {cards.map((rec) => (
                    <RecCard
                      key={rec.id}
                      rec={rec}
                      onApply={() => onApply(rec)}
                      onSearchNow={() => onSearchNow(rec)}
                      onDismiss={() => dismissMut.mutate(rec.id)}
                      applying={applyMut.isPending}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <PromptDialog
        open={promptOpen}
        onOpenChange={setPromptOpen}
        title="Your Discover prompt"
        description="Copy this into your AI of choice, then come back and paste its reply."
        prompt={prompt}
      />
      <PasteDialog
        open={pasteOpen}
        onOpenChange={setPasteOpen}
        title="Paste your AI's reply"
        description="Paste the whole answer — the JSON block is found automatically."
        submitLabel="Read recommendations"
        rows={10}
        pending={replyMut.isPending}
        onSubmit={onPaste}
      />
    </section>
  );
}

function RecCard({
  rec,
  onApply,
  onSearchNow,
  onDismiss,
  applying,
}: {
  rec: Recommendation;
  onApply: () => void;
  onSearchNow: () => void;
  onDismiss: () => void;
  applying: boolean;
}) {
  return (
    <div className="group border-border/60 bg-card relative flex flex-col rounded-lg border p-4">
      <div className="flex items-start justify-between gap-2">
        <h3 className="zg-serif text-foreground min-w-0 truncate text-base font-semibold">
          {rec.role}
        </h3>
        {rec.fit != null && <ScoreChip value={rec.fit} />}
      </div>

      {rec.why && (
        <p className="text-muted-foreground mt-2 text-sm leading-relaxed">
          {rec.why}
        </p>
      )}

      {rec.sample_titles.length > 0 && (
        <p className="text-muted-foreground mt-2 truncate text-xs">
          e.g. {rec.sample_titles.join(" · ")}
        </p>
      )}

      {rec.keywords.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {rec.keywords.map((k) => (
            <Badge key={k} variant="secondary" className="font-normal">
              {k}
            </Badge>
          ))}
        </div>
      )}

      <div className="mt-4 flex items-center gap-2 pt-1">
        <Button
          size="sm"
          variant={rec.applied ? "outline" : "default"}
          onClick={onApply}
          disabled={applying || rec.applied || rec.keywords.length === 0}
        >
          {rec.applied ? (
            <Check className="size-3.5" />
          ) : (
            <Plus className="size-3.5" />
          )}
          {rec.applied ? "In my searches" : "Add to my searches"}
        </Button>
        {rec.keywords.length > 0 && (
          <Button size="sm" variant="outline" onClick={onSearchNow}>
            <Search className="size-3.5" />
            Search now
          </Button>
        )}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="icon"
              variant="ghost"
              aria-label="Dismiss recommendation"
              className="text-muted-foreground hover:text-destructive ml-auto size-7"
              onClick={onDismiss}
            >
              <X className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Not for me</TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}
