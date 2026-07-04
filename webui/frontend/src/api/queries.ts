import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  endpoints,
  type TopPicksLimit,
  type TopPicksResponse,
  type TopPickRow,
  type BoardResponse,
  type BoardColumn,
  type BoardCardRow,
  type AppFields,
  type RoundFields,
} from "./client";

/* TanStack Query hooks for the shell's read/write endpoints. Phase 1+ builders:
 * follow this pattern — a `queryKey` const, a `useX()` reader, and a `useXMutation()`
 * that invalidates the relevant key. Keeps caching + refetch behavior uniform. */

export const queryKeys = {
  status: ["status"] as const,
  projects: ["projects"] as const,
  theme: ["theme"] as const,
  topPicks: (limit: TopPicksLimit) => ["toppicks", limit] as const,
  topPicksAll: ["toppicks"] as const,
  sourceKeys: ["source-keys"] as const,
  applications: (status?: string) => ["applications", status ?? "all"] as const,
  applicationsAll: ["applications"] as const,
  application: (id: number) => ["application", id] as const,
  board: ["board"] as const,
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
    onSuccess: () => {
      // A project switch changes basically everything the engine reads.
      qc.invalidateQueries();
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
