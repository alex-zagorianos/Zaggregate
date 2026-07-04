import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { endpoints } from "./client";

/* TanStack Query hooks for the shell's read/write endpoints. Phase 1+ builders:
 * follow this pattern — a `queryKey` const, a `useX()` reader, and a `useXMutation()`
 * that invalidates the relevant key. Keeps caching + refetch behavior uniform. */

export const queryKeys = {
  status: ["status"] as const,
  projects: ["projects"] as const,
  theme: ["theme"] as const,
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
