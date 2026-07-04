/* SSE run-console line handling — the pure core behind the "Update my Inbox now"
 * live log drawer. Kept out of the component (unit-tested in sse-console.test.ts,
 * node env) because the boundary de-dupe is subtle and load-bearing.
 *
 * THE BOUNDARY-DUPLICATE CONTRACT (webui/jobs.py::JobRunner.replay_lines): the SSE
 * route replays a job's buffered tail and THEN drains the live subscriber queue,
 * without an atomic barrier between the two. A single line that lands in that gap
 * can arrive BOTH in the replay and in the live drain. The runner docstring is
 * explicit that "SSE consumers must render lines idempotently — the frontend
 * console should de-dupe consecutive identical frames." So: we drop a line ONLY
 * when it is identical to the immediately-preceding line (a consecutive dup).
 *
 * We deliberately do NOT de-dupe non-adjacent repeats: a pipeline legitimately
 * prints the same text twice (e.g. "  scraping…" for two sources), and collapsing
 * those would lose real output. Only the adjacent replay/live boundary repeat —
 * the one the runner warns about — is suppressed. */

/** Append `line` to `prev`, suppressing it iff it exactly repeats the last line
 * already present (the runner's benign boundary duplication). Returns a NEW array
 * (never mutates `prev`) so it drops straight into React state setters. */
export function appendConsoleLine(
  prev: readonly string[],
  line: string,
): string[] {
  if (prev.length > 0 && prev[prev.length - 1] === line) {
    return prev as string[];
  }
  return [...prev, line];
}

/** Fold a whole batch of incoming lines onto `prev` with the same adjacent-dup
 * suppression applied across the join AND within the batch. Used when the SSE
 * `status` snapshot delivers a `lines_tail` array (reconnect / initial poll) or
 * when several frames are processed together. */
export function appendConsoleLines(
  prev: readonly string[],
  lines: readonly string[],
): string[] {
  const out = [...prev];
  for (const line of lines) {
    if (out.length === 0 || out[out.length - 1] !== line) out.push(line);
  }
  return out;
}

/** Cap the retained console to the last `max` lines so a very chatty run can't
 * grow the DOM/state unbounded (mirrors the server's bounded 2000-line deque).
 * Returns `lines` unchanged when already within the cap. */
export function capConsole(lines: string[], max = 2000): string[] {
  if (lines.length <= max) return lines;
  return lines.slice(lines.length - max);
}

/** Stick-to-bottom decision for auto-scroll. The console auto-scrolls to the newest
 * line UNLESS the user has scrolled up to read history. "At bottom" is measured
 * with a small tolerance (sub-pixel scroll + fractional line heights), so a user
 * who is essentially at the bottom keeps following the stream.
 *
 * @param scrollTop     element.scrollTop
 * @param scrollHeight  element.scrollHeight
 * @param clientHeight  element.clientHeight
 * @param tolerance     px slack that still counts as "at bottom" (default 24)
 */
export function isAtBottom(
  scrollTop: number,
  scrollHeight: number,
  clientHeight: number,
  tolerance = 24,
): boolean {
  return scrollHeight - (scrollTop + clientHeight) <= tolerance;
}
