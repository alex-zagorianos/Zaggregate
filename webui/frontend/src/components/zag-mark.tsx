/* The Zaggregate "Z" zag mark — an inline SVG port of ui/topbar.py::_draw_zmark:
 * a bold three-stroke zig-zag (top bar, diagonal, bottom bar) in a square box,
 * padded 18%, stroke width 12% of the box, round caps. Drawn on a 100×100
 * viewBox so it scales crisply; `currentColor` so callers set the accent via
 * text color. */
export function ZagMark({
  className,
  title = "Zaggregate",
}: {
  className?: string;
  title?: string;
}) {
  const pad = 18; // 18% of 100
  const x0 = pad;
  const y0 = pad;
  const x1 = 100 - pad;
  const y1 = 100 - pad;
  const w = 12; // stroke width = 12% of box
  return (
    <svg
      viewBox="0 0 100 100"
      className={className}
      role="img"
      aria-label={title}
      fill="none"
      stroke="currentColor"
      strokeWidth={w}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <title>{title}</title>
      <line x1={x0} y1={y0} x2={x1} y2={y0} /> {/* top bar */}
      <line x1={x1} y1={y0} x2={x0} y2={y1} /> {/* diagonal */}
      <line x1={x0} y1={y1} x2={x1} y2={y1} /> {/* bottom bar */}
    </svg>
  );
}
