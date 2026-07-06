"""Generate the app icon: ``data_static/zaggregate.ico`` (multi-size) from the
brand "Z" mark — an Aegean-blue rounded square with a white blocky Z, matching
``webui/frontend/public/favicon.svg`` (same geometry on a 64-unit viewBox).

Run once and commit the output (the .ico is a build input for app.spec's
``icon=`` and a runtime input for webui/native_win.apply_icon):

    py -3.12 scripts/make_icon.py

Drawn with PIL (already a shipped dependency via ttkbootstrap) at 16x
supersampling so the diagonal stays crisp when downscaled to 16 px.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

# Brand colors — ui/theme.py ACCENT ("Aegean / Greek-flag blue") + white mark.
BG = "#0d5eaf"
FG = "#ffffff"

# Geometry on the 64-unit viewBox shared with favicon.svg.
CANVAS = 64
CORNER_RADIUS = 14
Z_POINTS = [(18, 16), (46, 16), (46, 24), (31, 40), (46, 40),
            (46, 48), (18, 48), (18, 40), (33, 24), (18, 24)]

ICO_SIZES = [(256, 256), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]


def draw_mark(px: int) -> Image.Image:
    """Render the Z mark at ``px`` square, supersampled 16x for clean edges."""
    ss = 16
    big = px * ss
    scale = big / CANVAS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, big - 1, big - 1],
                        radius=int(CORNER_RADIUS * scale), fill=BG)
    d.polygon([(x * scale, y * scale) for x, y in Z_POINTS], fill=FG)
    return img.resize((px, px), Image.LANCZOS)


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "data_static" / "zaggregate.ico"
    base = draw_mark(256)
    base.save(out, format="ICO", sizes=ICO_SIZES)
    print(f"wrote {out} ({out.stat().st_size} bytes, sizes={ICO_SIZES})")


if __name__ == "__main__":
    main()
