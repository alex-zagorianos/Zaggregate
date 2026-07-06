import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  endpoints,
  importInbox,
  type TopPicksLimit,
  type TopPicksResponse,
  type TopPickRow,
  type BoardResponse,
  type BoardColumn,
  type BoardCardRow,
  type AppFields,
  type RoundFields,
  type InboxListResponse,
  type InboxRow,
  type ExportArgs,
  type ImportPolicy,
  type OnboardingAnswers,
  type CreateProjectArgs,
} from "./client";

/* TanStack Query hooks for the shell's read/write endpoints. Phase 1+ builders:
 * follow this pattern — a `queryKey` const, a `useX()` reader, and a `useXMutation()`
 * that invalidates the relevant key. Keeps caching + refetch behavior uniform. */

export const queryKeys = {
  status: ["status"] as const,
  projects: ["projects"] as const,
  theme: ["theme"] as const,
  notifyHighFit: ["notify-high-fit"] as const,
  topPicks: (limit: TopPicksLimit) => ["toppicks", limit] as const,
  topPicksAll: ["toppicks"] as const,
  sourceKeys: ["source-keys"] as const,
  applications: (status?: string) => ["applications", status ?? "all"] as const,
  applicationsAll: ["applications"] as const,
  application: (id: number) => ["application", id] as const,
  board: ["board"] as const,
  inbox: (params: Record<string, unknown>) => ["inbox", params] as const,
  inboxAll: ["inbox"] as const,
  inboxDetail: (id: number) => ["inbox-detail", id] as const,
  queue: ["queue"] as const,
  onboarding: ["onboarding"] as const,
  guide: ["guide"] as const,
  recommend: ["recommend"] as const,
  networkSummary: ["network-summary"] as const,
  insights: ["insights"] as const,
};

/* ── Coherent cross-tab invalidation ──────────────────────────────────────────
 * A status change ANYWHERE (Tracker quick-select, Board drop, JobDialog save)
 * must refresh the Tracker list + counts, the Board columns, the Top Picks
 * shortlist (a tracked/archived row may leave it), and any open detail. This one
 * helper is the single place that lists those keys, so every mutation stays in
 * sync by construction (plan requirement #5). */
function invalidateApplicationViews(
  qc: ReturnType<typeof useQueryClient>,
  id?: number,
) {
  qc.invalidateQueries({ queryKey: queryKeys.applicationsAll });
  qc.invalidateQueries({ queryKey: queryKeys.board });
  qc.invalidateQueries({ queryKey: queryKeys.topPicksAll });
  // The Apply Queue is "interested"-only, so any status move / archive can add or
  // remove a queue row — keep it coherent with the rest of the application views.
  qc.invalidateQueries({ queryKey: queryKeys.queue });
  if (id !== undefined) {
    qc.invalidateQueries({ queryKey: queryKeys.application(id) });
  }
}

export function useStatus() {
  return useQuery({
    queryKey: queryKeys.status,
    queryFn: () => endpoints.status(),
    staleTime: 30_000,
  });
}

export function useProjects() {
  return useQuery({
    queryKey: queryKeys.projects,
    queryFn: () => endpoints.projects(),
    staleTime: 30_000,
  });
}

export function useSwitchProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => endpoints.switchProject(slug),
    onSuccess: (res) => {
      if (res.pending_pinned) {
        // A run holds another project pinned; the switch is persisted and goes
        // live when the run finishes. Explain rather than look broken (the list
        // will still show the pinned project as active until then).
        toast.info("Switch saved", {
          description: "It'll take effect once the current run finishes.",
        });
      }
      // A project switch changes basically everything the engine reads.
      qc.invalidateQueries();
    },
    onError: () => {
      // A silently-dead switcher was the S39 bug shape — never fail mute again.
      toast.error("Couldn't switch project.");
    },
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: CreateProjectArgs) => endpoints.createProject(args),
    onSuccess: (res) => {
      // Always refresh the project list so the new campaign shows in the switcher.
      // When the create ALSO switched (args.switch), the new project became active
      // and the engine now reads a fresh, un-onboarded workspace — invalidate
      // everything so the onboarding gate re-reads and the wizard appears
      // naturally (that IS the new-project flow).
      if (res.active && res.active === res.slug) {
        qc.invalidateQueries();
      } else {
        qc.invalidateQueries({ queryKey: queryKeys.projects });
      }
    },
  });
}

// ── Top Picks ─────────────────────────────────────────────────────────────────

export function useTopPicks(limit: TopPicksLimit) {
  return useQuery({
    queryKey: queryKeys.topPicks(limit),
    queryFn: () => endpoints.topPicks(limit),
    staleTime: 15_000,
  });
}

/** Optimistically drop a row from EVERY cached Top Picks page (the row is moving
 * out of the inbox). Returns a snapshot so onError can roll back. Shared by
 * track + dismiss — the visual effect is identical (row leaves the list). */
function optimisticRemoveRow(
  qc: ReturnType<typeof useQueryClient>,
  inboxId: number,
) {
  const snapshots = qc.getQueriesData<TopPicksResponse>({
    queryKey: queryKeys.topPicksAll,
  });
  for (const [key, data] of snapshots) {
    if (!data) continue;
    qc.setQueryData<TopPicksResponse>(key, {
      ...data,
      rows: data.rows.filter((r: TopPickRow) => r.id !== inboxId),
    });
  }
  return snapshots;
}

export function useTrackInbox() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (inboxId: number) => endpoints.trackInbox(inboxId),
    onMutate: (inboxId) => {
      const snapshots = optimisticRemoveRow(qc, inboxId);
      return { snapshots };
    },
    onError: (_e, _v, ctx) => {
      // Roll the row(s) back into place on failure.
      ctx?.snapshots.forEach(([key, data]) => qc.setQueryData(key, data));
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: queryKeys.topPicksAll });
    },
  });
}

export function useDismissInbox() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (inboxId: number) => endpoints.dismissInbox(inboxId),
    onMutate: (inboxId) => {
      const snapshots = optimisticRemoveRow(qc, inboxId);
      return { snapshots };
    },
    onError: (_e, _v, ctx) => {
      ctx?.snapshots.forEach(([key, data]) => qc.setQueryData(key, data));
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: queryKeys.topPicksAll });
    },
  });
}

// ── Notification settings ─────────────────────────────────────────────────────

/** The "notify on high-fit matches" toggle (opt-in, default False). */
export function useNotifyHighFit() {
  return useQuery({
    queryKey: queryKeys.notifyHighFit,
    queryFn: () => endpoints.getNotifyHighFit(),
    staleTime: 30_000,
  });
}

export function useSetNotifyHighFit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (value: boolean) => endpoints.setNotifyHighFit(value),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.notifyHighFit });
    },
  });
}

// ── Source keys ───────────────────────────────────────────────────────────────

export function useSourceKeys() {
  return useQuery({
    queryKey: queryKeys.sourceKeys,
    queryFn: () => endpoints.sourceKeys(),
    staleTime: 10_000,
  });
}

export function useSaveSourceKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { source: string; fields: Record<string, string> }) =>
      endpoints.saveSourceKey(vars.source, vars.fields),
    onSuccess: () => {
      // Re-fetch the masked status so the field flips to "set / ••••1234".
      qc.invalidateQueries({ queryKey: queryKeys.sourceKeys });
    },
  });
}

/** Live-test is a pure action (no cache to invalidate); the component reads the
 * returned {status, detail} directly for inline feedback. */
export function useTestSourceKey() {
  return useMutation({
    mutationFn: (source: string) => endpoints.testSourceKey(source),
  });
}

// ── Applications (Tracker) ────────────────────────────────────────────────────

/** The Tracker list for a status view. `undefined`/"all" = every non-archived
 * row; "archived" = the archive view; a specific status filters within active. */
export function useApplications(status?: string) {
  return useQuery({
    queryKey: queryKeys.applications(status),
    queryFn: () => endpoints.listApplications(status),
    staleTime: 10_000,
  });
}

/** The one-call JobDialog payload (row + timeline + rounds + referral + status
 * vocabulary). Only fetched when a numeric id is open (edit mode). */
export function useApplication(id: number | null) {
  return useQuery({
    queryKey: queryKeys.application(id ?? -1),
    queryFn: () => endpoints.getApplication(id as number),
    enabled: id !== null,
    staleTime: 5_000,
  });
}

export function useAddApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (fields: AppFields) => endpoints.addApplication(fields),
    onSuccess: () => invalidateApplicationViews(qc),
  });
}

export function useUpdateApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; fields: AppFields }) =>
      endpoints.updateApplication(vars.id, vars.fields),
    onSuccess: (_res, vars) => invalidateApplicationViews(qc, vars.id),
  });
}

/** The funnel move — shared by the Tracker quick-status select AND the Board
 * drag-drop. Board drops pass optimistic context via the caller's onMutate; here
 * we only guarantee the coherent invalidation on settle. */
export function useSetApplicationStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; status: string }) =>
      endpoints.setApplicationStatus(vars.id, vars.status),
    onSuccess: (_res, vars) => invalidateApplicationViews(qc, vars.id),
  });
}

export function useArchiveApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => endpoints.archiveApplication(id),
    onSuccess: (_res, id) => invalidateApplicationViews(qc, id),
  });
}

export function useRestoreApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => endpoints.restoreApplication(id),
    onSuccess: (_res, id) => invalidateApplicationViews(qc, id),
  });
}

export function useDeleteApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => endpoints.deleteApplication(id),
    onSuccess: (_res, id) => invalidateApplicationViews(qc, id),
  });
}

// ── Notes + interview rounds (JobDialog sub-CRUD) ─────────────────────────────

export function useAddAppNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; note: string }) =>
      endpoints.addAppNote(vars.id, vars.note),
    onSuccess: (_res, vars) =>
      qc.invalidateQueries({ queryKey: queryKeys.application(vars.id) }),
  });
}

export function useAddRound() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; fields: RoundFields }) =>
      endpoints.addRound(vars.id, vars.fields),
    // A round can advance the funnel (engine coherence), so refresh all views.
    onSuccess: (_res, vars) => invalidateApplicationViews(qc, vars.id),
  });
}

export function useUpdateRound() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; rid: number; fields: RoundFields }) =>
      endpoints.updateRound(vars.id, vars.rid, vars.fields),
    onSuccess: (_res, vars) =>
      qc.invalidateQueries({ queryKey: queryKeys.application(vars.id) }),
  });
}

export function useDeleteRound() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; rid: number }) =>
      endpoints.deleteRound(vars.id, vars.rid),
    onSuccess: (_res, vars) =>
      qc.invalidateQueries({ queryKey: queryKeys.application(vars.id) }),
  });
}

// ── Board (Kanban) ────────────────────────────────────────────────────────────

export function useBoard() {
  return useQuery({
    queryKey: queryKeys.board,
    queryFn: () => endpoints.board(),
    staleTime: 10_000,
  });
}

/** Optimistically move a card between board columns. Removes it from its source
 * column and inserts it (status rewritten, forward_targets recomputed by the
 * server on refetch) at the top of the target column. Returns a snapshot so the
 * caller's onError can roll back. Shared move helper for the Board drop handler. */
export function optimisticMoveCard(
  qc: ReturnType<typeof useQueryClient>,
  cardId: number,
  targetStatus: string,
) {
  const prev = qc.getQueryData<BoardResponse>(queryKeys.board);
  if (!prev) return { prev };
  let moved: BoardCardRow | undefined;
  const stripped: BoardColumn[] = prev.columns.map((col) => {
    const keep: BoardCardRow[] = [];
    for (const c of col.cards) {
      if (c.id === cardId) moved = c;
      else keep.push(c);
    }
    return { ...col, cards: keep };
  });
  if (!moved) return { prev };
  const movedCard: BoardCardRow = { ...moved, status: targetStatus };
  const next: BoardColumn[] = stripped.map((col) =>
    col.status === targetStatus
      ? { ...col, cards: [movedCard, ...col.cards] }
      : col,
  );
  qc.setQueryData<BoardResponse>(queryKeys.board, { ...prev, columns: next });
  return { prev };
}

/** The board drag-drop move: optimistic reorder + POST status + rollback on
 * error, then the coherent invalidation so Tracker/Top-Picks/counts follow. */
export function useMoveCard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; status: string }) =>
      endpoints.setApplicationStatus(vars.id, vars.status),
    onMutate: (vars) => optimisticMoveCard(qc, vars.id, vars.status),
    onError: (_e, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(queryKeys.board, ctx.prev);
    },
    onSettled: (_res, _e, vars) => invalidateApplicationViews(qc, vars.id),
  });
}

// ── Inbox (flagship — Phase 3) ────────────────────────────────────────────────

/** Every inbox mutation (dismiss, undo, import, re-rank) can change the list, the
 * detail, the Top Picks shortlist (a re-rank reshuffles it), and the badges. This
 * one helper refreshes them all so the flagship stays coherent by construction. */
function invalidateInboxViews(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: queryKeys.inboxAll });
  qc.invalidateQueries({ queryKey: queryKeys.topPicksAll });
}

/** The filtered inbox list. `params` is the mapped query-param object
 * (lib/inbox-filter-state.toParams); the key includes it so each distinct view
 * caches independently. `keepPreviousData` keeps the old rows on screen while a
 * filter change refetches (no flash to empty), which the roving-focus table
 * needs. */
export function useInbox(
  params: Record<string, string | number | boolean | undefined>,
) {
  return useQuery<InboxListResponse>({
    queryKey: queryKeys.inbox(params),
    queryFn: () => endpoints.inbox(params),
    staleTime: 10_000,
    placeholderData: (prev) => prev,
  });
}

/** Detail for the selected row (fit-why, score breakdown, ghost, ATS, preview).
 * Only fetched when a row is selected. */
export function useInboxDetail(id: number | null) {
  return useQuery({
    queryKey: queryKeys.inboxDetail(id ?? -1),
    queryFn: () => endpoints.inboxDetail(id as number),
    enabled: id !== null,
    staleTime: 30_000,
  });
}

/** Optimistically drop rows from EVERY cached inbox page + Top Picks (they're
 * moving out of the inbox). Returns snapshots so onError can roll back. Shared by
 * single + bulk dismiss and by track. */
function optimisticRemoveInboxRows(
  qc: ReturnType<typeof useQueryClient>,
  ids: number[],
) {
  const idSet = new Set(ids);
  const inboxSnaps = qc.getQueriesData<InboxListResponse>({
    queryKey: queryKeys.inboxAll,
  });
  for (const [key, data] of inboxSnaps) {
    if (!data) continue;
    const kept = data.rows.filter((r: InboxRow) => !idSet.has(r.id));
    const removed = data.rows.length - kept.length;
    qc.setQueryData<InboxListResponse>(key, {
      ...data,
      rows: kept,
      // Keep the "N of M" honest as rows leave optimistically.
      shown: Math.max(0, data.shown - removed),
      total: Math.max(0, data.total - removed),
    });
  }
  const picksSnaps = qc.getQueriesData<TopPicksResponse>({
    queryKey: queryKeys.topPicksAll,
  });
  for (const [key, data] of picksSnaps) {
    if (!data) continue;
    qc.setQueryData<TopPicksResponse>(key, {
      ...data,
      rows: data.rows.filter((r: TopPickRow) => !idSet.has(r.id)),
    });
  }
  return { inboxSnaps, picksSnaps };
}

function rollbackInboxRows(
  qc: ReturnType<typeof useQueryClient>,
  ctx:
    | {
        inboxSnaps: [readonly unknown[], unknown][];
        picksSnaps: [readonly unknown[], unknown][];
      }
    | undefined,
) {
  ctx?.inboxSnaps.forEach(([key, data]) => qc.setQueryData(key, data));
  ctx?.picksSnaps.forEach(([key, data]) => qc.setQueryData(key, data));
}

/** Track an inbox row (promote to tracker). Optimistic removal + coherent
 * invalidation across inbox, Top Picks, and the application views. */
export function useTrackInboxRow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => endpoints.trackInbox(id),
    onMutate: (id) => optimisticRemoveInboxRows(qc, [id]),
    onError: (_e, _v, ctx) => rollbackInboxRows(qc, ctx),
    onSettled: () => {
      invalidateInboxViews(qc);
      invalidateApplicationViews(qc);
    },
  });
}

/** Dismiss a single inbox row (optimistic). */
export function useDismissInboxRow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => endpoints.dismissInbox(id),
    onMutate: (id) => optimisticRemoveInboxRows(qc, [id]),
    onError: (_e, _v, ctx) => rollbackInboxRows(qc, ctx),
    onSettled: () => invalidateInboxViews(qc),
  });
}

/** Bulk-dismiss many rows (optimistic). Resolves to the response so the caller
 * can surface the undo_token in its Undo toast. */
export function useDismissBulk() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: number[]) => endpoints.dismissBulk(ids),
    onMutate: (ids) => optimisticRemoveInboxRows(qc, ids),
    onError: (_e, _v, ctx) => rollbackInboxRows(qc, ctx),
    onSettled: () => invalidateInboxViews(qc),
  });
}

/** Restore a dismissed batch (undo). No token = the most recent batch. */
export function useUndoDismiss() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (undoToken?: string) => endpoints.undoDismiss(undoToken),
    onSuccess: () => invalidateInboxViews(qc),
  });
}

/** Revert the last AI re-rank (any route). */
export function useUndoRerank() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => endpoints.undoRerank(),
    onSuccess: () => invalidateInboxViews(qc),
  });
}

/** Export the inbox (or the current view) for AI ranking → file list. Pure action
 * (no cache change); the caller reads the returned files for download buttons. */
export function useExportInbox() {
  return useMutation({
    mutationFn: (args: ExportArgs) => endpoints.exportInbox(args),
  });
}

/** Import an AI-returned re-rank (file or pasted text). Refreshes the inbox +
 * Top Picks on success (scores landed on rows). */
export function useImportInbox() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      input: { file: File } | { text: string };
      policy: ImportPolicy;
    }) => importInbox(vars.input, vars.policy),
    onSuccess: () => invalidateInboxViews(qc),
  });
}

/** Paste an AI fit reply → score the currently-unscored rows. */
export function useScoreReply() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (text: string) => endpoints.scoreReply(text),
    onSuccess: () => invalidateInboxViews(qc),
  });
}

// ── Apply Queue (Phase 4) ─────────────────────────────────────────────────────

/** The ranked apply queue (interested applications, fit-else-score desc). The
 * server returns rows already in order; the tab renders them as-is. */
export function useQueue() {
  return useQuery({
    queryKey: queryKeys.queue,
    queryFn: () => endpoints.queue(),
    staleTime: 10_000,
  });
}

/** Refresh the queue + the other application views after a queue mutation (docs
 * saved, generated, fit-scores applied). The queue's own rows change (docs/fit) and
 * a fit re-rank reshuffles Top Picks, so the shared application invalidation covers
 * it. Returned as a callback the imperative queue flows call in their onSuccess. */
export function useInvalidateQueueViews() {
  const qc = useQueryClient();
  return React.useCallback(() => {
    qc.invalidateQueries({ queryKey: queryKeys.queue });
    invalidateApplicationViews(qc);
  }, [qc]);
}

// ── Onboarding (Phase 5) ──────────────────────────────────────────────────────

/** The onboarding gate + prefill. Read once at app start to decide whether to
 * show the welcome takeover; `staleTime: Infinity` so it doesn't refetch (the
 * flag only flips on a Finish, which invalidates it explicitly). */
export function useOnboarding() {
  return useQuery({
    queryKey: queryKeys.onboarding,
    queryFn: () => endpoints.onboarding(),
    staleTime: Infinity,
  });
}

/** Apply the wizard answers (or the AI express lane). Onboarding rewrites the
 * project config + preferences, which changes essentially every engine read, so
 * a success invalidates everything (like a project switch) plus the onboarding
 * flag itself so the gate closes. */
export function useApplyOnboarding() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (answers: OnboardingAnswers) =>
      endpoints.applyOnboarding(answers),
    onSuccess: () => {
      qc.invalidateQueries();
    },
  });
}

/** Apply the AI express-lane config block. Same broad invalidation as the wizard
 * apply (it writes the same on-disk contract). */
export function useApplyAiSetup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (text: string) => endpoints.applyAiSetup(text),
    onSuccess: () => {
      qc.invalidateQueries();
    },
  });
}

/** Apply ONE combined AI reply (S40 AI-first setup): splits config + seeds, applies
 * the config synchronously, and (autorun, default true) chains the first-run job
 * (seed companies → first daily search). Same broad invalidation as the plain AI
 * apply — it writes the same on-disk config contract, so essentially every engine
 * read changes; the started job (job_id) streams over SSE and its console does the
 * inbox/top-picks refresh on finish. `autorun` lets the caller choose whether to
 * kick off the search (wizard: true; Search-tab dialog: false → a "Run now" button). */
export function useApplyAiSetupFull() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { text: string; autorun: boolean }) =>
      endpoints.applyAiSetupFull(vars.text, vars.autorun),
    onSuccess: () => {
      qc.invalidateQueries();
    },
  });
}

// ── Guide (Phase 5) ───────────────────────────────────────────────────────────

/** The static in-app Guide sections. Content is effectively constant, so a long
 * stale time avoids refetching as the user flips tabs. */
export function useGuide() {
  return useQuery({
    queryKey: queryKeys.guide,
    queryFn: () => endpoints.guide(),
    staleTime: Infinity,
  });
}

// ── Discover (EXPERIMENTAL, S36c) ─────────────────────────────────────────────

export function useRecommend() {
  return useQuery({
    queryKey: queryKeys.recommend,
    queryFn: () => endpoints.recommend(),
    staleTime: 30_000,
  });
}

export function useRecommendReply() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (text: string) => endpoints.recommendReply(text),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.recommend });
    },
  });
}

export function useRecommendApply() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => endpoints.recommendApplyKeywords(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.recommend });
    },
  });
}

export function useRecommendDismiss() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => endpoints.recommendDismiss(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.recommend });
    },
  });
}

// ── Insights (B6) ─────────────────────────────────────────────────────────────

/** The read-only Insights payload (funnel + by_source + cadence). Recomputed
 * over the tracker DB on each visit; a short stale time keeps it fresh after a
 * status change without hammering the route as the user flips tabs. */
export function useInsights() {
  return useQuery({
    queryKey: queryKeys.insights,
    queryFn: () => endpoints.insights(),
    staleTime: 10_000,
  });
}

// ── Referral network (B4) ─────────────────────────────────────────────────────

/** The imported-network overview for the Sources card. */
export function useNetworkSummary() {
  return useQuery({
    queryKey: queryKeys.networkSummary,
    queryFn: () => endpoints.networkSummary(),
    staleTime: 30_000,
  });
}

/** Import a connections CSV (raw text, read client-side). Refreshes the summary
 * AND every open inbox/application detail (a new match can now appear). */
export function useNetworkImport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { text: string; source: "linkedin" | "google" }) =>
      endpoints.networkImport(vars.text, vars.source),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.networkSummary });
      qc.invalidateQueries({ queryKey: ["inbox-detail"] });
      qc.invalidateQueries({ queryKey: ["application"] });
    },
  });
}

/** Forget the whole imported network. Same coherent refresh as import. */
export function useNetworkClear() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => endpoints.networkClear(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.networkSummary });
      qc.invalidateQueries({ queryKey: ["inbox-detail"] });
      qc.invalidateQueries({ queryKey: ["application"] });
    },
  });
}
