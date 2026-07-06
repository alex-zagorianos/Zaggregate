/* Port of ui/palette.py::filter_commands — the Ctrl+K palette ranking.
 *
 * Rank rules, faithful to the Python (which has a small unit test there too):
 *   1. Direct substring matches first, EARLIER match-position first.
 *   2. Then scattered-subsequence matches (every query char appears in order).
 *   3. Ties broken alphabetically (case-insensitive).
 *   4. Empty query returns all labels in their original order.
 * Case-insensitive throughout. Pure + unit-tested (filter-commands.test.ts).
 */

/** Does every char of `q` appear in `low` in order (a subsequence)? Mirrors the
 * Python `it = iter(low); all(ch in it for ch in q)` consuming-iterator trick. */
function isSubsequence(q: string, low: string): boolean {
  let i = 0;
  for (const ch of low) {
    if (i < q.length && ch === q[i]) i++;
  }
  return i === q.length;
}

export function filterCommands<T extends string>(
  labels: readonly T[],
  query: string,
): T[] {
  const q = (query || "").trim().toLowerCase();
  if (!q) return [...labels];

  const scored: Array<{ tier: number; pos: number; label: T }> = [];
  for (const lab of labels) {
    const low = lab.toLowerCase();
    const pos = low.indexOf(q);
    if (pos !== -1) {
      scored.push({ tier: 0, pos, label: lab });
      continue;
    }
    if (isSubsequence(q, low)) {
      scored.push({ tier: 1, pos: 0, label: lab });
    }
  }
  scored.sort((a, b) => {
    if (a.tier !== b.tier) return a.tier - b.tier;
    if (a.pos !== b.pos) return a.pos - b.pos;
    return a.label.toLowerCase().localeCompare(b.label.toLowerCase());
  });
  return scored.map((s) => s.label);
}
