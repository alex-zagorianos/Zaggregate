/* Pure decision logic behind the AI-setup panes (components/ai-setup-dialog.tsx) —
 * extracted so it's unit-testable in the node vitest env (this project has no React
 * Testing Library; component render/interaction can't be tested here — see
 * brain/techdebt-register #21). The panes import these so the component stays thin
 * presentation over a tested core. */

import type {
  AiSetupApplied,
  AiSetupApplyResponse,
  ApplyAiSetupFullResponse,
} from "@/api/client";

/** Which prompt/apply contract a pane instance drives. */
export type AiSetupPromptKind = "config" | "full";

/** The result handed to `onApplied` — a discriminated union so a "full" caller can
 * read `job_id`/`seed_count` while a "config" caller just reads `applied`. */
export type AiSetupResult =
  | { kind: "config"; applied: AiSetupApplied }
  | ({ kind: "full" } & ApplyAiSetupFullResponse);

/** Normalize a config-apply response into an AiSetupResult (kind "config"). */
export function configResult(res: AiSetupApplyResponse): AiSetupResult {
  return { kind: "config", applied: res.applied };
}

/** Normalize a full-apply response into an AiSetupResult (kind "full"). */
export function fullResult(res: ApplyAiSetupFullResponse): AiSetupResult {
  return { kind: "full", ...res };
}

/** The started first-run job id to attach a console to, or null (config kind, or a
 * full reply where autorun was off / a run was already in flight). */
export function resultJobId(res: AiSetupResult): string | null {
  return res.kind === "full" ? res.job_id : null;
}

/** The human "couldn't start the run" reason, if any (only a full reply carries it). */
export function resultJobError(res: AiSetupResult): string | undefined {
  return res.kind === "full" ? res.job_error : undefined;
}

/** Whether the applied summary should show a "starter companies" row: only for a
 * full reply that actually carried seeds (config-only replies apply cleanly and
 * simply don't show a 0-count row — inclusion over precision). */
export function showsSeedRow(res: AiSetupResult): boolean {
  return res.kind === "full" && res.seed_count > 0;
}
