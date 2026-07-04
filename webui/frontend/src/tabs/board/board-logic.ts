/* Pure kanban drag-drop rules for the Board tab. The SERVER decides which moves
 * are legal (GET /api/board gives every card a `forward_targets` list computed by
 * ui.kanban_core.forward_targets); the client only enforces the same list for the
 * drag affordance + optimistic move. Keeping the guard here (not in the component)
 * makes it unit-testable in the node vitest env and guarantees the board and the
 * engine agree on legality. */

export interface BoardCard {
  id: number;
  status?: string | null;
  forward_targets: string[];
  [key: string]: unknown;
}

/** True when a card may be dropped into `targetStatus`. A card can always be
 * "dropped" back onto its own column (a no-op, so dragging and releasing in place
 * never errors); otherwise the target must be in the card's server-supplied
 * forward_targets. A terminal card (forward_targets: []) can only no-op. */
export function canDrop(card: BoardCard, targetStatus: string): boolean {
  if (targetStatus === (card.status ?? "")) return true;
  return card.forward_targets.includes(targetStatus);
}

/** True when the drop actually changes the card's status (i.e. a real move, not a
 * release-in-place). Used to skip the POST on a no-op drop. */
export function isRealMove(card: BoardCard, targetStatus: string): boolean {
  return canDrop(card, targetStatus) && targetStatus !== (card.status ?? "");
}

/** A human explanation for an INVALID drop, for the snap-back toast. Names the
 * from/to labels so the user learns the rule ("Can't move Interview → Applied —
 * the board only advances forward"). `labelOf` resolves a status to its label. */
export function rejectReason(
  card: BoardCard,
  targetStatus: string,
  labelOf: (s: string) => string,
): string {
  const from = labelOf(card.status ?? "");
  const to = labelOf(targetStatus);
  if (card.forward_targets.length === 0) {
    return `${from} is a final stage — reopen it from the job editor if you need to.`;
  }
  return `Can't move ${from} → ${to}. The board only advances forward; use the job editor to correct a status.`;
}
