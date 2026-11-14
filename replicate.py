#!/usr/bin/env python3
"""
replicate.py - reproduce a reference drawing on the real field:work app.

Strategy: the app has no flood fill, so flat color regions become dense
scanline strokes (one horizontal line per row-run of the region's mask,
width >= spacing so they merge into a solid fill). Outlines come from
draw_with_code.py trace mode (contour strokes, no hatching) and are drawn
last, on top of the fills - exactly how the original was inked.

Usage:
  # 1. make the outline strokes with trace mode (contours only, no hatching)
  python3 draw_with_code.py trace --photo reference.jpg --max-strokes 4000 \
      --density 0.6 --out ref_lines.png

  # 2. build the combined stroke list (fills + outlines)
  python3 replicate.py --build --photo reference.jpg \
      --lines ref_lines.strokes.json --out replica.strokes.json

  # 3. or do both build AND replay into the app in one go
  python3 replicate.py --run --photo reference.jpg --lines ref_lines.strokes.json

Deps: pillow numpy scipy (all in requirements.txt).
"""

import argparse
import json
import os
import sys
import time

import numpy as np
from PIL import Image
from scipy import ndimage

# (name, mask predicate on (R,G,B) int arrays, fill hex or None=mean, min area)
def masks(R, G, B):
    return [
        ("pink",   (R > 190) & (R - B > 35) & (R - G > 45), None, 250),
        ("red",    (R > 150) & (G < 115) & (B < 115) & (R - G > 55), "#c14d40", 150),
        ("yellow", (R > 220) & (G > 190) & (B < 120), "#f3da4c", 150),
        ("green",  (G > R + 25) & (G > B + 25) & (G > 110), "#6fa66f", 100),
        ("tan",    (R > 175) & (R < 228) & (G > 140) & (G < 195)
                   & (B > 100) & (B < 160) & (R - B > 45) & (R - B < 110), None, 400),
        ("cream",  (R > 200) & (R < 235) & (G > 190) & (G < 225)
                   & (B > 170) & (B < 205) & (R - B > 15) & (R - B < 45), None, 400),
        ("dark",   (R < 95) & (G < 95) & (B < 95), None, 250),
    ]


def clean_hex(rgb):
    return "#%02x%02x%02x" % tuple(int(round(c)) for c in rgb)


def fill_strokes(mask, color, spacing=6, width=7, scale=2):
    """Scanline strokes over a boolean mask, in x2 (supersampled) coords."""
    strokes = []
    for row in range(0, mask.shape[0], spacing):
        xs = np.flatnonzero(mask[row])
        if xs.size == 0:
            continue
        breaks = np.flatnonzero(np.diff(xs) > 2)
        starts = np.concatenate(([0], breaks + 1))
        ends = np.concatenate((breaks, [xs.size - 1]))
        for s, e in zip(starts, ends):
            if xs[e] - xs[s] < 5:
                continue
            y = row * scale
            strokes.append({
                "points": [[int(xs[s]) * scale, y], [int(xs[e]) * scale, y]],
                "color": color, "width": width * scale,
            })
    return strokes


def build(photo, lines, out):
    img = np.asarray(Image.open(photo).convert("RGB")).astype(int)
    R, G, B = img[:, :, 0], img[:, :, 1], img[:, :, 2]
    strokes = []
    counts = {}
    for name, mask, fixed, min_area in masks(R, G, B):
        lab, n = ndimage.label(mask)
        for i in range(1, n + 1):
            comp = lab == i
            area = int(comp.sum())
            if area < min_area:
                continue
            color = fixed or clean_hex(img[comp].mean(axis=0))
            fs = fill_strokes(comp, color)
            strokes.extend(fs)
            counts[f"{name}#{i}"] = (area, color, len(fs))
    for k, v in sorted(counts.items()):
        print(f"  {k}: area={v[0]} color={v[1]} strokes={v[2]}")

    lines_payload = json.load(open(lines))
    strokes.extend(lines_payload["strokes"])  # outlines on top
    json.dump({"source_size": lines_payload["source_size"], "strokes": strokes},
              open(out, "w"))
    print(f"total {len(strokes)} strokes -> {out}")
    return out


def run(args):
    # fieldwork_server.py lives next to this script
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from fieldwork_server import BrowserDriver, act_replay, act_png, act_format
    path = build(args.photo, args.lines, args.out)
    payload = json.load(open(path))
    d = BrowserDriver(headless=not args.show, browser=args.browser)
    # the reference is landscape: switch the app to a landscape format so
    # the replica fills the page instead of letterboxing inside 4:5
    act_format(d, args.format)
    print("replaying...")
    t0 = time.time()
    r = act_replay(d, payload["strokes"], source_size=payload["source_size"],
                   clear_first=True, pace_ms=0)
    print(r, f"wall {time.time()-t0:.0f}s")
    time.sleep(1)
    with open(args.export, "wb") as f:
        f.write(act_png(d))
    print(f"saved {args.export}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Reproduce a reference drawing on the real field:work app.")
    ap.add_argument("--build", action="store_true",
                    help="build the combined stroke list only")
    ap.add_argument("--run", action="store_true",
                    help="build AND replay into the app, then export the PNG")
    ap.add_argument("--photo", default="reference.jpg",
                    help="reference photo to replicate (default: reference.jpg)")
    ap.add_argument("--lines", default="ref_lines.strokes.json",
                    help="outline strokes from draw_with_code.py trace "
                         "(default: ref_lines.strokes.json)")
    ap.add_argument("--out", default="replica.strokes.json",
                    help="combined stroke list to write "
                         "(default: replica.strokes.json)")
    ap.add_argument("--export", default="replica_export.png",
                    help="where --run saves the app's PNG export "
                         "(default: replica_export.png)")
    ap.add_argument("--format", default="16:9",
                    choices=("1:1", "4:5", "5:4", "9:16", "16:9"),
                    help="app page format for --run (default: 16:9, landscape "
                         "like the original reference)")
    ap.add_argument("--browser", choices=("chrome", "chromium"),
                    default="chrome",
                    help="browser for --run (default: installed Google Chrome, "
                         "falling back to bundled Chromium)")
    ap.add_argument("--show", action="store_true",
                    help="--run with a visible browser window (default: "
                         "headless)")
    a = ap.parse_args()
    if a.run:
        run(a)
    else:
        build(a.photo, a.lines, a.out)
