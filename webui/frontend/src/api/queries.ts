import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  endpoints,
  type TopPicksLimit,
  type TopPicksResponse,
  type TopPickRow,
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
};

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
