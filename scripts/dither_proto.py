"""Dithered area chart — prototype, Alpine Wash only, no dependency.

Oscar saw dither-kit (tripwire.sh/dither-kit) and wanted the look. The library
is wrong for us and the reasons are concrete, not taste:

  - its `color` prop accepts only "green|blue|purple|pink|orange|red|grey".
    No custom hex. Alpine Wash is #17283A / #223A4E / #C67C3E. The library
    cannot render our brand, so adopting it ships a SECOND brand into the
    product we spent 2026-07-15 unifying.
  - "no dependencies" is not true: the docs list motion, d3, Tailwind, shadcn.
  - no ARIA, no screen-reader path, no data-table fallback; `interactive:false`
    is documented as "decorative spark, no crosshair or tooltip".
  - license unspecified, and this repo is MIT and vendors its fonts with OFL.

But dithering is a TECHNIQUE, not a library. This is it, in our tokens, in ~35
lines: Bayer-8 ordered dither where density carries the value, so the shape
reads without a gridline.

Where it belongs: trend shapes — gold-history, MemoryHealthTrend, Runs
sparklines. Where it does NOT: the Judge tab, which exists to show 0.962 vs
0.808 vs 0.923. Dithering trades precision for texture, and on that chart the
number IS the argument.

Run: python3 scripts/dither_proto.py  ->  /tmp/dither-gold.png
Next step is porting these 35 lines to <canvas> in web/src.
"""
import json

from PIL import Image, ImageDraw

PAPER = (0xEC, 0xE4, 0xD8)
INK = (0x17, 0x28, 0x3A)
ACCENT = (0x22, 0x3A, 0x4E)
IMPROVE = (0xC6, 0x7C, 0x3E)  # reserved for improvement; rule growth IS improvement

BAYER8 = [[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26],
          [12, 44, 4, 36, 14, 46, 6, 38], [60, 28, 52, 20, 62, 30, 54, 22],
          [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
          [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]]


def dither_area(d, series, x0, y0, w, h, top, bot, scale):
    lo, hi = min(series), max(series)
    span = (hi - lo) or 1
    n = len(series)

    def height_at(px):
        t = px / max(w - 1, 1) * (n - 1)
        i = min(int(t), n - 2)
        f = t - i
        v = series[i] + (series[i + 1] - series[i]) * f
        return (v - lo) / span

    for px in range(w):
        colh = height_at(px) * (h - 2) + 2
        for py in range(h):
            if (h - py) > colh:
                continue
            frac = (h - py) / max(colh, 1)
            if frac < BAYER8[py % 8][px % 8] / 64.0:
                continue
            c = tuple(int(bot[k] + (top[k] - bot[k]) * (1 - frac)) for k in range(3))
            d.rectangle([x0 + px * scale, y0 + py * scale,
                         x0 + px * scale + scale - 1, y0 + py * scale + scale - 1],
                        fill=c)


if __name__ == "__main__":
    S, W, H = 3, 300, 74
    img = Image.new("RGB", (W * S + 80, H * S + 96), PAPER)
    d = ImageDraw.Draw(img)
    hist = [json.loads(l) for l in open("data/gold-history.jsonl") if l.strip()]
    # a compile emitted `1` once (data bug, worth chasing); it is not a rule count
    series = [x["total"] for x in hist if x["total"] > 10]
    d.text((40, 30), "GOLDEN RULES", fill=(0x4E, 0x61, 0x73))
    d.text((40, 48), f"{series[-1]}", fill=INK)
    d.text((78, 52), f"+{series[-1] - series[0]} learned", fill=IMPROVE)
    dither_area(d, series, 40, 90, W, H, IMPROVE, ACCENT, S)
    img.save("/tmp/dither-gold.png")
    print(f"  /tmp/dither-gold.png — {series[0]} -> {series[-1]} rules")
