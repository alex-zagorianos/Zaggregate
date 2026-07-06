/* Presentational label helpers for the Board cards.
 *
 * The server (ui/kanban_core.days_label) emits a bare day count: "today" for a
 * same-day card, "1 day" / "N days" otherwise (or "" when unknown). The board card
 * used to render `${days_label} here`, which read as "today here". This maps the
 * bare label to a natural card line. Pure + unit-tested (board-labels.test.ts). */

/** "today" → "added today"; "1 day" → "1 day here"; "N days" → "N days here";
 * "" → "" (the caller omits the line entirely). */
export function daysInStageLabel(daysLabel: string): string {
  const s = (daysLabel ?? "").trim();
  if (!s) return "";
  if (s === "today") return "added today";
  return `${s} here`;
}
