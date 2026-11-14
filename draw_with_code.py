#!/usr/bin/env python3
"""
draw_with_code.py - actually draw with code at the field:work event.

Two modes:

  decide  A local Ollaya decision model picks every mark (shape, direction,
          length, color, pressure, pen-lift) via POST /v1/systemone.
          "It decides, it doesn't generate." Falls back to a seeded random
          chooser if the daemon is not running, so the demo never dies.

          Add --live and decide skips nothing but goes further: after the
          PNG and strokes file are written, it opens the real field:work
          app and draws the marks on it, stroke by stroke, at a watchable
          speed (same --speed/--format/--clear/--browser/--headless family
          as trace --live).

  trace   Photo -> algorithmic ink sketch. Deterministic edge-following
          strokes + shadow hatching. Point it at a photo of the model:
          python3 draw_with_code.py trace --photo model.jpg --out sketch.png

          Add --live and trace skips the export-only path after writing the
          PNG: it opens the real field:work app and draws the sketch on it,
          stroke by stroke, at a watchable speed (--speed strokes/sec).

          The sketch is not stuck as plain pencil: --tool paint|boids draws
          with the platform's Paint stamps or Boids flocks, --opacity sets
          translucency, and --preset breathing|nervous|... applies the app's
          living system presets so the drawing stays alive. These ride along
          inside the stroke file, so they work the same for /replay, --live
          and --codegen scripts.

Deps: pip install pillow numpy   (that's all)
Tested output lands next to the script; open the PNG in Preview and it
auto-refreshes as the drawing grows (decide saves every --save-every steps).

Both modes also write a stroke list next to the PNG (drawing.strokes.json):
every mark as {points, color, width}. Replay it onto the real event platform
(field-work-drawing.web.app) through fieldwork_server.py:
  python3 fieldwork_server.py            # then
  curl -X POST 127.0.0.1:7766/replay -H 'Content-Type: application/json' \
       -d @drawing.strokes.json

Examples:
  python3 draw_with_code.py decide --mood "calm seated pose, flowing ink" --steps 400
  python3 draw_with_code.py decide --steps 200 --live --speed 20
  python3 draw_with_code.py decide --model largha --steps 200 --seed 7
  python3 draw_with_code.py trace --photo pose.jpg --out pose_sketch.png
  python3 draw_with_code.py trace --photo pose.jpg --live --speed 20
  python3 draw_with_code.py trace --photo pose.jpg --style ink-wash --live
  python3 draw_with_code.py trace --photo pose.jpg --tool paint --paint-shape o \
      --opacity 0.5 --preset breathing --live

  trace --style bundles six curated artist styles (gesture, ink-wash, stipple,
  blueprint, swarm, field-notes). A style sets tool/preset/opacity/ink/paper
  and generation knobs to a tuned look; explicit flags override the bundle,
  and --color overrides its ink.
"""

import argparse
import base64
import json
import math
import random
import sys
import time
import urllib.request
import urllib.error
import zlib

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

DEFAULT_API = "http://127.0.0.1:11435"
DEFAULT_MODEL = "laya:en"

PALETTE = {
    "charcoal": (43, 43, 43),
    "indigo": (59, 74, 107),
    "rust": (181, 82, 58),
    "ochre": (201, 143, 46),
    "sage": (107, 127, 94),
    "plum": (122, 74, 99),
}
PAPER = (250, 248, 245)


# ---------------------------------------------------------------- styles ---

# Curated artist-style presets for trace --style. Each style is a bundle of
# the existing knobs (tool/shape/preset/opacity/ink/paper + stroke-generation
# parameters) tuned to a look. Explicit flags always win over the style's
# bundle, and --color overrides the style's ink.
#
# Performance: the app slows superlinearly past a few hundred Paint stamps,
# and Boids keep simulating after the stroke ends, so the paint/boids styles
# (stipple, swarm) cap their stroke counts low. Raise them with explicit
# --max-strokes only if you enjoy slideshows.
STYLES = {
    "gesture": {
        "blurb": "few bold strokes, big brush, nervous preset - a 2-minute "
                 "live-model sketch",
        "preset": "nervous",
        "opacity": 1.0,
        "ink": "#1a1a1a",
        "paper": "#faf8f5",
        "width_scale": 4.5,
        "gen": {"edge_pct": 4.0, "max_strokes": 400, "density": 0.2,
                "shadow_level": 0.45, "length_scale": 2.5},
    },
    "ink-wash": {
        "blurb": "soft grays, low-opacity layered strokes, breathing preset - "
                 "moody, good for portraits",
        "preset": "breathing",
        "opacity": 0.45,
        "width_scale": 1.5,
        "paper": "#faf8f5",
        "gen": {"edge_pct": 5.0, "max_strokes": 2500, "density": 0.5,
                "shadow_level": 0.55},
    },
    "stipple": {
        "blurb": "dots with density mapped to shading - pointillism. Uses "
                 "single-point draw strokes: a one-tap Paint gesture sprays "
                 "dozens of stamps, so Paint is the wrong tool for dots",
        "tool": "draw", "opacity": 0.9,
        "ink": "#26221e",
        "paper": "#faf8f5",
        "gen": {"mode": "stipple", "max_strokes": 4000},
    },
    "blueprint": {
        "blurb": "white ink on dark blue paper, ruler-straight, frozen preset "
                 "- technical drawing",
        "preset": "frozen",
        "opacity": 1.0,
        "ink": "#f2f6ff",
        "paper": "#1d3a6e",
        "width_scale": 1.1,
        "gen": {"edge_pct": 4.0, "max_strokes": 2200, "density": 0.35,
                "shadow_level": 0.5, "jitter": 0.1},
    },
    "swarm": {
        "blurb": "the sketch drawn by a boid flock, wandering preset - "
                 "chaotic but alive; demo showpiece",
        "tool": "boids", "boid_preset": "stream", "boid_shape": "dot",
        "preset": "wandering",
        "opacity": 1.0,
        "ink": "#1a1a1a",
        "paper": "#faf8f5",
        "width_scale": 3.0,
        "gen": {"edge_pct": 2.5, "max_strokes": 400, "density": 0.45,
                "hatch": False, "length_scale": 2.0},
    },
    "field-notes": {
        "blurb": "sepia ink, slightly restless, sketchy double-lines - "
                 "Da Vinci notebook energy",
        "preset": "restless",
        "opacity": 0.85,
        "ink": "#6b4423",
        "paper": "#faf8f5",
        "double_line": True,
        "gen": {"edge_pct": 5.0, "max_strokes": 1500, "density": 0.3,
                "shadow_level": 0.5},
    },
}


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


# ------------------------------------------------------- stroke recording ---

class Recorder:
    """Same call shape as the PIL ImageDraw subset used here, but appends
    replayable strokes: {"points": [[x, y], ...], "color": "#rrggbb",
    "width": px}. This is the bridge to the real field:work app."""

    def __init__(self):
        self.strokes = []

    @staticmethod
    def _hex(fill):
        return "#%02x%02x%02x" % tuple(fill[:3])

    def line(self, xy, fill, width=1, joint=None):
        if xy and not isinstance(xy[0], (list, tuple)):
            pts = [[float(xy[i]), float(xy[i + 1])] for i in range(0, len(xy), 2)]
        else:
            pts = [[float(p[0]), float(p[1])] for p in xy]
        self.strokes.append({"points": pts, "color": self._hex(fill),
                             "width": float(width)})

    def arc(self, box, start, end, fill, width=1):
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        rx, ry = (box[2] - box[0]) / 2, (box[3] - box[1]) / 2
        pts = []
        for i in range(25):
            a = math.radians(start + (end - start) * i / 24)
            pts.append([cx + rx * math.cos(a), cy + ry * math.sin(a)])
        self.strokes.append({"points": pts, "color": self._hex(fill),
                             "width": float(width)})

    def ellipse(self, box, fill):
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        r = max((box[2] - box[0]) / 2, 1)
        # one point + wide brush = a dot on the app (round single-point fill)
        self.strokes.append({"points": [[cx, cy]], "color": self._hex(fill),
                             "width": float(2 * r)})


class TeeDraw:
    """Fans every draw call out to PIL (for the PNG) and a Recorder (for
    the replayable stroke list)."""

    def __init__(self, draw, rec):
        self.draw, self.rec = draw, rec

    def line(self, *a, **k):
        self.draw.line(*a, **k)
        self.rec.line(*a, **k)

    def arc(self, *a, **k):
        self.draw.arc(*a, **k)
        self.rec.arc(*a, **k)

    def ellipse(self, *a, **k):
        self.draw.ellipse(*a, **k)
        self.rec.ellipse(*a, **k)


def save_strokes(rec, path, size, preset=None, paper=None):
    payload = {"source_size": list(size), "strokes": rec.strokes}
    if preset:
        payload["preset"] = preset
    if paper:
        payload["paper"] = paper
    with open(path, "w") as f:
        json.dump(payload, f)
    return path


def stamp_technique(strokes, args):
    """Bake --tool/--opacity/--shape choices into every stroke so replays
    (HTTP /replay, --live, --codegen scripts) draw with them. Keys a stroke
    already carries (e.g. a style's hand-tuned echo strokes) are kept. The
    preview PNG is unaffected: PIL always renders plain ink lines."""
    for s in strokes:
        if args.tool != "draw":
            s.setdefault("tool", args.tool)
        if args.opacity is not None:
            s.setdefault("opacity", round(args.opacity, 3))
        if args.tool == "paint" and args.paint_shape:
            s.setdefault("shape", args.paint_shape)
        if args.tool == "boids":
            if args.boid_shape:
                s.setdefault("shape", args.boid_shape)
            if args.boid_preset:
                s.setdefault("boid_preset", args.boid_preset)


# ------------------------------------------------------------- live draw ---

APP_FORMATS = ["1:1", "4:5", "5:4", "9:16", "16:9"]


def draw_strokes_live(payload, speed=30.0, headless=False, browser="chrome",
                      format=None, clear=False, on_chunk=None):
    """Replay a stroke list onto the live field:work app, chunk by chunk, at
    a watchable speed. payload is the shape save_strokes writes:
    {"source_size": [w, h], "strokes": [...]}. The replay scales the list
    into the app's current page format (or --format) and letterboxes when
    the aspect ratios differ.

    on_chunk, when given, is called after each ~1s chunk as
    on_chunk(driver, strokes_done, strokes_total) - a hook for tests and
    progress screenshots.
    """
    try:
        from fieldwork_server import BrowserDriver, act_format, act_replay
    except ImportError as e:
        sys.exit(f"--live needs Playwright and fieldwork_server.py next to "
                 f"this script ({e}). Set up with:\n"
                 f"  pip install playwright\n"
                 f"  python3 -m playwright install chromium   # Chrome fallback")
    d = BrowserDriver(headless=headless, browser=browser)
    try:
        if format:
            act_format(d, format)
        strokes = payload["strokes"]
        paper = payload.get("paper")
        pace_ms = max(0, int(round(1000.0 / speed))) if speed > 0 else 0
        chunk = max(1, int(round(speed)))  # ~1s of drawing per replay call
        total = len(strokes)
        done = 0
        t0 = time.time()
        r = None
        for i in range(0, total, chunk):
            r = act_replay(d, strokes[i:i + chunk],
                           source_size=payload.get("source_size"),
                           clear_first=clear and i == 0, pace_ms=pace_ms,
                           paper=paper if i == 0 else None)
            done += r["replayed"]
            print(f"  live: {done}/{total} strokes", flush=True)
            if on_chunk:
                on_chunk(d, done, total)
        dt = time.time() - t0
        print(f"live draw done: {done} strokes in {dt:.1f}s on {d.url} "
              f"(page {r['page'][0]}x{r['page'][1]}, scale {r['scale']})")
        if not headless and sys.stdin.isatty():
            input("press Enter to close the browser...")
    finally:
        # the browser lives on the driver's worker thread; close it there
        try:
            d.call(lambda dd: dd.browser.close())
        except Exception:
            pass
        d.jobs.put(None)

# ---------------------------------------------------------------- ollaya ---

def ollaya_decide(api_base, model, state, questions, timeout=10):
    """One /v1/systemone call. Returns answers dict, or None on any failure."""
    body = json.dumps({
        "model": model,
        "state": state,
        "questions": questions,
    }).encode()
    req = urllib.request.Request(
        api_base.rstrip("/") + "/v1/systemone",
        data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer local"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode())
        return payload.get("answers")
    except Exception:
        return None


def build_questions():
    return {
        "mark": {
            "type": "choice",
            "instructions": "You are the planning brain of an ink artist doing a generative life drawing. Which mark should the brush make next?",
            "criteria": {
                "line":  "a single confident straight stroke",
                "curve": "a flowing curved stroke, like a contour of a shoulder",
                "arc":   "a partial circle, suggests volume",
                "cross": "a small cross-hatch mark, adds texture",
                "dot":   "a single stipple dot, adds quiet detail",
            },
        },
        "direction": {
            "type": "choice",
            "instructions": "How should the brush change direction for this next mark, given its recent path?",
            "criteria": {
                "continue":    "keep going the same way",
                "drift-left":  "curve gently left",
                "drift-right": "curve gently right",
                "turn-back":   "reverse, echo a previous line",
                "jump":        "lift and leap to a fresh spot",
            },
        },
        "length": {
            "type": "choice",
            "instructions": "How long should this mark be?",
            "criteria": {"short": "a short gesture", "medium": "a medium stroke", "long": "a long sweeping stroke"},
        },
        "color": {
            "type": "choice",
            "instructions": "Which ink color fits the mood and the recent marks? Vary it when the drawing feels flat.",
            "criteria": {name: f"{name} ink" for name in PALETTE},
        },
        "pressure": {
            "type": "score",
            "instructions": "How hard should the brush press? 0 = hairline whisper, 2 = heavy bold ink.",
            "criteria": ["light hairline", "medium stroke", "heavy bold"],
        },
        "lift_pen": {
            "type": "noul",
            "instructions": "The artist should lift the pen after this mark and start a fresh stroke elsewhere.",
        },
    }


# ------------------------------------------------------------ primitives ---

class Brush:
    def __init__(self, w, h, rng):
        self.x, self.y = w / 2, h / 2
        self.heading = rng.uniform(0, 2 * math.pi)
        self.w, self.h = w, h
        self.rng = rng

    def steer(self, choice):
        if choice == "drift-left":
            self.heading -= self.rng.uniform(0.15, 0.6)
        elif choice == "drift-right":
            self.heading += self.rng.uniform(0.15, 0.6)
        elif choice == "turn-back":
            self.heading += math.pi + self.rng.uniform(-0.3, 0.3)
        elif choice == "jump":
            self.x = self.rng.uniform(0.1 * self.w, 0.9 * self.w)
            self.y = self.rng.uniform(0.1 * self.h, 0.9 * self.h)
            self.heading = self.rng.uniform(0, 2 * math.pi)
        # "continue": nothing

    def clamp(self):
        m = 20
        bounced = False
        if self.x < m or self.x > self.w - m:
            self.heading = math.pi - self.heading
            bounced = True
        if self.y < m or self.y > self.h - m:
            self.heading = -self.heading
            bounced = True
        self.x = min(max(self.x, m), self.w - m)
        self.y = min(max(self.y, m), self.h - m)
        return bounced


def draw_mark(draw, brush, mark, length_px, color, width, rng):
    x0, y0 = brush.x, brush.y
    dx, dy = math.cos(brush.heading), math.sin(brush.heading)
    x1, y1 = x0 + dx * length_px, y0 + dy * length_px

    if mark == "line":
        draw.line([x0, y0, x1, y1], fill=color, width=width)
    elif mark == "curve":
        # quadratic bezier with a perpendicular control offset
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        bend = rng.uniform(-0.6, 0.6) * length_px
        cx, cy = mx - dy * bend, my + dx * bend
        pts = []
        for t in np.linspace(0, 1, 24):
            px = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t ** 2 * x1
            py = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t ** 2 * y1
            pts.append((px, py))
        draw.line(pts, fill=color, width=width, joint="curve")
    elif mark == "arc":
        r = max(length_px / 2, 6)
        start = math.degrees(brush.heading) + rng.uniform(-40, 40)
        box = [x0 - r, y0 - r, x0 + r, y0 + r]
        draw.arc(box, start=start, end=start + rng.uniform(60, 200),
                 fill=color, width=width)
    elif mark == "cross":
        s = max(width * 2, 6)
        draw.line([x0 - s, y0 - s, x0 + s, y0 + s], fill=color, width=max(1, width - 1))
        draw.line([x0 - s, y0 + s, x0 + s, y0 - s], fill=color, width=max(1, width - 1))
    elif mark == "dot":
        r = max(width, 2)
        draw.ellipse([x0 - r, y0 - r, x0 + r, y0 + r], fill=color)

    brush.x, brush.y = x1, y1
    brush.clamp()


# ------------------------------------------------------------- mode: decide

def _clip_decide_segment(p0, p1, width, height):
    """Clip one recorded decide-mode segment to the export canvas."""
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0), (dx, width - x0),
                 (-dy, y0), (dy, height - y0)):
        if p == 0:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return None
            t0 = max(t0, r)
        else:
            if r < t0:
                return None
            t1 = min(t1, r)
    a = [min(width, max(0.0, x0 + t0 * dx)),
         min(height, max(0.0, y0 + t0 * dy))]
    b = [min(width, max(0.0, x0 + t1 * dx)),
         min(height, max(0.0, y0 + t1 * dy))]
    return a, b, t0, t1


def _format_decide_strokes(strokes, scale, ox, oy, width, height):
    """Scale strokes into a formatted canvas and clip paths to its bounds."""
    formatted = []
    eps = 1e-7
    for stroke in strokes:
        pts = [[p[0] * scale + ox, p[1] * scale + oy]
               for p in stroke["points"]]
        groups = []
        if len(pts) == 1:
            x, y = pts[0]
            if 0 <= x <= width and 0 <= y <= height:
                groups.append([pts[0]])
        else:
            current = None
            for p0, p1 in zip(pts, pts[1:]):
                clipped = _clip_decide_segment(p0, p1, width, height)
                if clipped is None:
                    if current:
                        groups.append(current)
                        current = None
                    continue
                a, b, t0, t1 = clipped
                if current and math.dist(current[-1], a) <= eps:
                    if math.dist(current[-1], b) > eps:
                        current.append(b)
                else:
                    if current:
                        groups.append(current)
                    current = [a]
                    if math.dist(a, b) > eps:
                        current.append(b)
                if t1 < 1 - eps:
                    groups.append(current)
                    current = None
            if current:
                groups.append(current)
        for group in groups:
            item = dict(stroke)
            item["points"] = group
            item["width"] = max(0.5, stroke["width"] * scale)
            formatted.append(item)
    return formatted


def run_decide(args):
    rng = random.Random(args.seed)
    W, H = args.size
    SS = 2  # supersample for anti-aliasing
    img = Image.new("RGB", (W * SS, H * SS), PAPER)
    rec = Recorder()
    draw = TeeDraw(ImageDraw.Draw(img), rec)
    brush = Brush(W * SS, H * SS, rng)
    questions = build_questions()
    recent = []
    used_api = False
    t0 = time.time()

    for step in range(args.steps):
        state = {
            "step": step,
            "of": args.steps,
            "mood": args.mood,
            "brush": {
                "x_pct": round(brush.x / (W * SS), 2),
                "y_pct": round(brush.y / (H * SS), 2),
                "heading_deg": round(math.degrees(brush.heading)),
            },
            "recent_marks": recent[-5:],
        }
        answers = ollaya_decide(args.api_base, args.model, state, questions)
        if answers is not None:
            used_api = True
            mark = answers["mark"]["choice"]
            direction = answers["direction"]["choice"]
            length = answers["length"]["choice"]
            color = answers["color"]["choice"]
            pressure = answers["pressure"]["score"]
            lift = answers["lift_pen"]["noul"]
        else:
            if step == 0:
                print("! ollaya daemon not reachable - using the seeded random "
                      "fallback so the demo still runs. Start it with: ollaya serve",
                      file=sys.stderr)
            mark = rng.choices(["line", "curve", "arc", "cross", "dot"],
                               weights=[35, 35, 12, 8, 10])[0]
            direction = rng.choices(["continue", "drift-left", "drift-right", "turn-back", "jump"],
                                    weights=[40, 25, 25, 4, 6])[0]
            length = rng.choices(["short", "medium", "long"], weights=[30, 45, 25])[0]
            color = rng.choices(list(PALETTE), weights=[40, 14, 12, 12, 11, 11])[0]
            pressure = rng.uniform(0, 2)
            lift = rng.random() * 0.6

        # sanitize (a small model can always surprise you)
        if mark not in ("line", "curve", "arc", "cross", "dot"):
            mark = "line"
        if direction not in ("continue", "drift-left", "drift-right", "turn-back", "jump"):
            direction = "continue"
        if color not in PALETTE:
            color = "charcoal"
        length_px = {"short": 30, "medium": 80, "long": 160}.get(length, 80) * SS * args.scale
        width = max(1, int((1 + pressure * 3) * SS))
        rgb = PALETTE[color]

        brush.steer(direction)
        draw_mark(draw, brush, mark, length_px, rgb, width, rng)
        recent.append(f"{color} {mark}")
        if isinstance(lift, (int, float)) and lift > 0.7:
            brush.steer("jump")

        if (step + 1) % args.save_every == 0 or step == args.steps - 1:
            img.resize((W, H), Image.LANCZOS).save(args.out)

    sw, sh = W, H
    if args.format:
        fw, fh = (int(x) for x in args.format.split(":"))
        # canvas: the largest fw:fh rectangle that fits inside --size
        if W / H > fw / fh:
            ch_, cw_ = H, round(H * fw / fh)
        else:
            cw_, ch_ = W, round(W * fh / fw)
        s = min(cw_ * SS / img.width, ch_ * SS / img.height)
        dw, dh = max(1, round(img.width * s)), max(1, round(img.height * s))
        ox, oy = (cw_ * SS - dw) // 2, (ch_ * SS - dh) // 2
        canvas = Image.new("RGB", (cw_ * SS, ch_ * SS), PAPER)
        canvas.paste(img.resize((dw, dh), Image.LANCZOS), (ox, oy))
        img = canvas
        rec.strokes = _format_decide_strokes(
            rec.strokes, s, ox, oy, cw_ * SS, ch_ * SS)
        sw, sh = cw_, ch_
        print(f"format: letterboxed to {args.format} ({sw}x{sh})")

    img.resize((sw, sh), Image.LANCZOS).save(args.out)
    strokes_path = save_strokes(rec, args.strokes, (sw * SS, sh * SS))
    dt = time.time() - t0
    print(f"done: {args.steps} marks in {dt:.1f}s "
          f"({'ollaya /v1/systemone' if used_api else 'random fallback'}, "
          f"model={args.model}) -> {args.out} + {strokes_path}")

    if args.live:
        payload = {"source_size": [W * SS, H * SS], "strokes": rec.strokes}
        draw_strokes_live(
            payload,
            speed=args.speed, headless=args.headless, browser=args.browser,
            format=args.format, clear=args.clear)


# -------------------------------------------------------------- mode: trace

def sobel(gray):
    kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=float) / 4.0
    ky = kx.T
    p = np.pad(gray, 1, mode="edge")
    gx = sum(p[i:i + gray.shape[0], j:j + gray.shape[1]] * kx[i, j]
             for i in range(3) for j in range(3))
    gy = sum(p[i:i + gray.shape[0], j:j + gray.shape[1]] * ky[i, j]
             for i in range(3) for j in range(3))
    return gx, gy


CODEGEN_TEMPLATE = '''#!/usr/bin/env python3
"""Redraw {name} on the field:work drawing platform.

Generated by draw_with_code.py trace --codegen. Share this file with anyone:

  1. they start the driver:  python3 fieldwork_server.py
  2. they run this script:   python3 {script_name}

It replays {n_strokes} strokes through the local API at 127.0.0.1:7766
(about 700 strokes/sec; set PACE_MS below to watch it draw slowly).
Brush settings (tool, opacity, living preset) travel inside the stroke data.
"""

import base64
import json
import urllib.request
import zlib

API = "http://127.0.0.1:7766"
PACE_MS = {pace_ms}   # ms between strokes; 0 = as fast as the app goes
CLEAR_FIRST = False   # True wipes the canvas before drawing

_PAYLOAD = "{payload}"


def main():
    payload = json.loads(zlib.decompress(base64.b64decode(_PAYLOAD)))
    payload["pace_ms"] = PACE_MS
    payload["clear_first"] = CLEAR_FIRST
    req = urllib.request.Request(
        API + "/replay",
        data=json.dumps(payload).encode(),
        headers={{"Content-Type": "application/json"}},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        print(r.read().decode())


if __name__ == "__main__":
    main()
'''


def write_codegen(path, name, strokes, size, pace_ms=0, preset=None,
                  paper=None):
    body = {"source_size": list(size), "strokes": strokes}
    if preset:
        body["preset"] = preset
    if paper:
        body["paper"] = paper
    payload = json.dumps(body, separators=(",", ":"))
    blob = base64.b64encode(zlib.compress(payload.encode(), 9)).decode()
    script = CODEGEN_TEMPLATE.format(
        name=name, script_name=path.rsplit("/", 1)[-1],
        n_strokes=len(strokes), pace_ms=pace_ms, payload=blob)
    with open(path, "w") as f:
        f.write(script)
    return path


def run_trace(args):
    rng = random.Random(args.seed)
    W, H = args.size
    photo = Image.open(args.photo)
    src = photo.convert("L")
    src.thumbnail((W, H), Image.LANCZOS)
    sw, sh = src.size
    gray = np.asarray(src, dtype=float) / 255.0
    color_arr = (np.asarray(photo.convert("RGB").resize((sw, sh), Image.LANCZOS))
                 if args.color else None)
    gx, gy = sobel(gray)
    mag = np.hypot(gx, gy)

    SS = 2
    style_ink = hex_rgb(args.style_ink) if args.style_ink else None
    jt = args.jitter
    ws = args.width_scale
    img = Image.new("RGB", (sw * SS, sh * SS), args.style_paper or PAPER)
    rec = Recorder()
    draw = TeeDraw(ImageDraw.Draw(img), rec)

    # --- pass 1: strokes along strong edges (contours)
    threshold = max(np.percentile(mag, 100 - args.edge_pct), 0.06)
    ys, xs = np.where(mag > threshold)
    order = (np.argsort(-mag[ys, xs]) if args.gen_mode == "sketch"
             else [])  # strongest edges first
    max_contour = int(args.max_strokes * args.density)
    # min-distance claiming: an edge band yields one row of strokes, not a fill
    claimed = np.zeros((sh, sw), dtype=bool)
    spacing = max(2, int(4 / args.density))
    placed = 0
    for idx in order:
        if placed >= max_contour:
            break
        y, x = ys[idx], xs[idx]
        if claimed[y, x]:
            continue
        y0, y1 = max(0, y - spacing), min(sh, y + spacing + 1)
        x0, x1 = max(0, x - spacing), min(sw, x + spacing + 1)
        claimed[y0:y1, x0:x1] = True
        placed += 1
        # edge direction is perpendicular to the gradient
        ang = math.atan2(gy[y, x], gx[y, x]) + math.pi / 2
        strength = min(mag[y, x] / (mag.max() + 1e-9), 1.0)
        ln = (6 + 18 * strength) * SS * args.length_scale
        wid = max(1, int((1 + 2 * strength) * SS * 0.8 * ws))
        jx, jy = rng.uniform(-1.5, 1.5) * SS * jt, rng.uniform(-1.5, 1.5) * SS * jt
        cx, cy = x * SS + jx, y * SS + jy
        dx, dy = math.cos(ang) * ln / 2, math.sin(ang) * ln / 2
        if color_arr is not None:
            r, g, b = (int(c) for c in color_arr[y, x])
            ink = (r, g, b)
        elif style_ink is not None:
            ink = style_ink
        else:
            shade = int(40 + 120 * (1 - strength))
            ink = (shade, shade, shade)
        draw.line([cx - dx, cy - dy, cx + dx, cy + dy],
                  fill=ink, width=wid)

    # --- pass 2: hatching in dark areas (shadow)
    cell = 9
    dark = (gray < args.shadow_level) & (args.gen_mode == "sketch") & args.hatch
    for cy in range(0, sh - cell, cell):
        for cx in range(0, sw - cell, cell):
            block = gray[cy:cy + cell, cx:cx + cell]
            darkness = 1 - block.mean()
            if not dark[cy:cy + cell, cx:cx + cell].any():
                continue
            n = int(darkness * args.density * 3)
            base_ang = math.pi / 4 if (cx // cell + cy // cell) % 2 == 0 else -math.pi / 4
            for _ in range(n):
                px = (cx + rng.uniform(1, cell - 1)) * SS
                py = (cy + rng.uniform(1, cell - 1)) * SS
                ln = cell * 0.7 * SS
                a = base_ang + rng.uniform(-0.15, 0.15) * jt
                dx, dy = math.cos(a) * ln / 2, math.sin(a) * ln / 2
                if style_ink is not None:
                    ink = style_ink
                else:
                    shade = int(90 + 90 * (1 - darkness))
                    ink = (shade, shade, shade)
                draw.line([px - dx, py - dy, px + dx, py + dy],
                          fill=ink, width=max(1, int(SS * ws)))

    # --- stipple mode: dots instead of lines, density mapped to shading.
    # Only cells clearly darker than mid-gray contribute (a low threshold
    # floods the picture with uniform noise dots, drowning the figure), and
    # the stroke cap is spread over the whole picture via a first measuring
    # pass instead of being spent on the top rows. Each dot is a 1px micro
    # line, not a tap: down+up at one point double-registers on the app.
    if args.gen_mode == "stipple":
        ink = style_ink or (38, 34, 30)
        cell = 6
        cells = []
        total = 0.0
        for cy in range(0, sh - cell, cell):
            for cx in range(0, sw - cell, cell):
                darkness = 1 - gray[cy:cy + cell, cx:cx + cell].mean()
                if darkness < 0.3:
                    continue
                e = ((darkness - 0.3) / 0.7) ** 2.0 * 3 * args.density
                cells.append((cx, cy, darkness, e))
                total += e
        k = min(1.0, args.max_strokes / total) if total > 0 else 1.0
        for cx, cy, darkness, e in cells:
            if placed >= args.max_strokes:
                break
            if e < 0.25:  # too faint to matter, whatever the cap allows
                continue
            expected = e * k
            n = int(expected)
            if rng.random() < expected - n:
                n += 1
            for _ in range(min(n, args.max_strokes - placed)):
                px = (cx + rng.uniform(0.5, cell - 0.5)) * SS
                py = (cy + rng.uniform(0.5, cell - 0.5)) * SS
                r = (1.5 + 2.5 * darkness) * SS
                draw.line([px, py, px + 1.2, py], fill=ink,
                          width=max(2, int(2 * r)))
                placed += 1

    # --- style post-pass: sketchy double-lines (a lighter offset echo of
    # every stroke, replayed as one group after the main strokes)
    if args.double_line:
        base = list(rec.strokes)
        pil = ImageDraw.Draw(img)
        for s in base:
            pts = [[p[0] + 2.5 * SS + rng.uniform(-1, 1),
                    p[1] + 2.0 * SS + rng.uniform(-1, 1)] for p in s["points"]]
            col = hex_rgb(s["color"])
            w = max(1, int(round(s["width"] * 0.7)))
            if len(pts) > 1:
                pil.line([c for p in pts for c in p], fill=col, width=w)
            else:
                r = max(1, w // 2)
                pil.ellipse([pts[0][0] - r, pts[0][1] - r,
                             pts[0][0] + r, pts[0][1] + r], fill=col)
            rec.strokes.append({"points": pts, "color": s["color"],
                                "width": float(w),
                                "opacity": round((args.opacity or 1.0) * 0.45, 3)})

    img = img.filter(ImageFilter.GaussianBlur(0.4))

    # --- optional canvas format: letterbox onto a --format aspect canvas.
    # The static export fits the photo inside --size, so without this the
    # PNG/strokes keep the photo's aspect and --format only affects --live.
    if args.format:
        fw, fh = (int(x) for x in args.format.split(":"))
        # canvas: the largest fw:fh rectangle that fits inside --size
        if W / H > fw / fh:
            ch_, cw_ = H, round(H * fw / fh)
        else:
            cw_, ch_ = W, round(W * fh / fw)
        s = min(cw_ * SS / img.width, ch_ * SS / img.height)
        dw, dh = max(1, round(img.width * s)), max(1, round(img.height * s))
        ox, oy = (cw_ * SS - dw) // 2, (ch_ * SS - dh) // 2
        canvas = Image.new("RGB", (cw_ * SS, ch_ * SS),
                           args.style_paper or PAPER)
        canvas.paste(img.resize((dw, dh), Image.LANCZOS), (ox, oy))
        img = canvas
        for st in rec.strokes:
            st["points"] = [[p[0] * s + ox, p[1] * s + oy]
                            for p in st["points"]]
            st["width"] = max(0.5, st["width"] * s)
        sw, sh = cw_, ch_
        print(f"format: letterboxed to {args.format} ({sw}x{sh})")

    img.resize((sw, sh), Image.LANCZOS).save(args.out)
    stamp_technique(rec.strokes, args)
    strokes_path = save_strokes(rec, args.strokes, (sw * SS, sh * SS),
                                preset=args.preset, paper=args.style_paper)
    print(f"done: traced {args.photo} -> {args.out} + {strokes_path} "
          f"({placed} contour strokes + hatching, {len(rec.strokes)} total)")

    if args.codegen:
        cg = write_codegen(args.codegen, args.photo, rec.strokes,
                           (sw * SS, sh * SS), pace_ms=args.pace_ms,
                           preset=args.preset, paper=args.style_paper)
        print(f"codegen: {cg} (share this file; it redraws via the local API)")

    if args.live:
        payload = {"source_size": [sw * SS, sh * SS], "strokes": rec.strokes}
        if args.preset:
            payload["preset"] = args.preset
        if args.style_paper:
            payload["paper"] = args.style_paper
        draw_strokes_live(
            payload,
            speed=args.speed, headless=args.headless, browser=args.browser,
            format=args.format, clear=args.clear)


# ------------------------------------------------------------------- cli ---

def apply_style(args):
    """Resolve trace options: explicit flag > --style bundle > built-in
    default. Runs after parsing, before validation."""
    style = STYLES.get(args.style) or {}
    gen = style.get("gen", {})
    for name, default in (("edge_pct", 6.0), ("max_strokes", 9000),
                          ("density", 1.0), ("shadow_level", 0.55)):
        if getattr(args, name) is None:
            setattr(args, name, gen.get(name, default))
    for name, default in (("tool", "draw"), ("paint_shape", None),
                          ("boid_shape", None), ("boid_preset", None),
                          ("opacity", None), ("preset", None)):
        if getattr(args, name) is None:
            setattr(args, name, style.get(name, default))
    args.style_ink = None if args.color else style.get("ink")
    args.style_paper = style.get("paper")
    args.width_scale = style.get("width_scale", 1.0)
    args.double_line = style.get("double_line", False)
    args.gen_mode = gen.get("mode", "sketch")
    args.jitter = gen.get("jitter", 1.0)
    args.hatch = gen.get("hatch", True)
    args.length_scale = gen.get("length_scale", 1.0)


def add_live_args(p, live_help):
    """The --live flag family shared by decide and trace: draw the strokes
    on the live app, at a watchable pace, through the same code path."""
    p.add_argument("--live", action="store_true", help=live_help)
    p.add_argument("--speed", type=float, default=30.0,
                   help="live draw speed in strokes per second (default 30; "
                        "lower looks more hand-drawn, 0 = as fast as the app goes)")
    p.add_argument("--format", choices=APP_FORMATS, default=None,
                   help="letterbox the static export to this aspect; with "
                        "--live also set the app's page format")
    p.add_argument("--clear", action="store_true",
                   help="clear the app canvas before drawing live")
    p.add_argument("--browser", choices=("chrome", "chromium"), default="chrome",
                   help="browser for --live (default: installed Google Chrome, "
                        "falling back to bundled Chromium)")
    p.add_argument("--headless", action="store_true",
                   help="--live without a visible window (for testing)")


def parse_size(s):
    w, h = s.lower().split("x")
    return int(w), int(h)


def main():
    ap = argparse.ArgumentParser(
        description="Draw with code: ollaya decision-model painter + photo tracer.",
        epilog="decide mode talks to the ollaya daemon at --api-base "
               "(default 127.0.0.1:11435) and falls back to random if it is down.")
    sub = ap.add_subparsers(dest="mode", required=True)

    d = sub.add_parser("decide", help="ollaya decision-model painter")
    d.add_argument("--model", default=DEFAULT_MODEL)
    d.add_argument("--api-base", default=DEFAULT_API)
    d.add_argument("--mood", default="calm seated pose, flowing ink, confident single strokes")
    d.add_argument("--steps", type=int, default=400)
    d.add_argument("--size", type=parse_size, default="1000x1400")
    d.add_argument("--scale", type=float, default=1.0, help="stroke length multiplier")
    d.add_argument("--seed", type=int, default=None)
    d.add_argument("--save-every", type=int, default=20)
    d.add_argument("--out", default="drawing.png")
    d.add_argument("--strokes", default=None,
                   help="stroke-list JSON for replay (default: <out>.strokes.json)")
    add_live_args(d, "after deciding, draw the marks on the live app "
                     "(field-work-drawing.web.app) in a browser window")
    d.set_defaults(fn=run_decide)

    t = sub.add_parser("trace", help="photo -> algorithmic ink sketch")
    t.add_argument("--photo", required=True)
    t.add_argument("--out", default="sketch.png")
    t.add_argument("--size", type=parse_size, default="1000x1400")
    t.add_argument("--style", choices=list(STYLES), default=None,
                   help="curated artist-style preset bundle: gesture, "
                        "ink-wash, stipple, blueprint, swarm, field-notes. "
                        "Sets tool/preset/opacity/ink and generation knobs "
                        "to a tuned look; explicit flags override the bundle, "
                        "and --color overrides its ink")
    t.add_argument("--edge-pct", type=float, default=None,
                   help="percent of pixels treated as contour (2-12; "
                        "default 6.0, or the style's)")
    t.add_argument("--max-strokes", type=int, default=None,
                   help="cap on contour strokes (default 9000, or the "
                        "style's cap)")
    t.add_argument("--density", type=float, default=None,
                   help="stroke density multiplier (default 1.0, or the "
                        "style's)")
    t.add_argument("--shadow-level", type=float, default=None,
                   help="gray level below which hatching appears (0-1; "
                        "default 0.55, or the style's)")
    t.add_argument("--seed", type=int, default=None)
    t.add_argument("--strokes", default=None,
                   help="stroke-list JSON for replay (default: <out>.strokes.json)")
    add_live_args(t, "after tracing, draw the sketch on the live app "
                     "(field-work-drawing.web.app) in a browser window")
    t.add_argument("--color", action="store_true",
                   help="sample the photo's colors per stroke instead of "
                        "grayscale ink")
    t.add_argument("--tool", choices=("draw", "paint", "boids"), default=None,
                   help="platform tool the strokes replay with: paint (stamp "
                        "fill) or boids (flock). Affects the app replay, not "
                        "the preview PNG (default draw, or the style's)")
    t.add_argument("--paint-shape", choices=("o", "x", "+", "square", "diamond"),
                   default=None, help="stamp shape for --tool paint")
    t.add_argument("--boid-shape", choices=("dot", "arrow", "chevron", "dash"),
                   default=None, help="boid shape for --tool boids")
    t.add_argument("--boid-preset",
                   choices=("stream", "drizzle", "crowd", "crawl", "rush",
                            "scatter"),
                   default=None, help="flock behavior preset for --tool boids")
    t.add_argument("--opacity", type=float, default=None, metavar="0.05-1",
                   help="brush opacity for every stroke (app replay only)")
    t.add_argument("--preset",
                   choices=("held", "breathing", "restless", "wandering",
                            "nervous", "melting", "frozen"),
                   default=None,
                   help="living system preset applied to the drawing on "
                        "replay (breathing, nervous, ...): the app keeps "
                        "animating the lines afterward")
    t.add_argument("--codegen", default=None, metavar="OUT.py",
                   help="also write a standalone redraw script: share it, and "
                        "whoever runs it (with fieldwork_server.py up) redraws "
                        "the picture through the local API")
    t.add_argument("--pace-ms", type=int, default=0,
                   help="ms between strokes inside the --codegen script "
                        "(default 0 = full speed; ~30 looks hand-drawn)")
    t.set_defaults(fn=run_trace)

    args = ap.parse_args()
    if args.mode == "trace":
        apply_style(args)
        if args.paint_shape and args.tool != "paint":
            ap.error("--paint-shape needs --tool paint")
        if (args.boid_shape or args.boid_preset) and args.tool != "boids":
            ap.error("--boid-shape/--boid-preset need --tool boids")
        if args.opacity is not None and not 0.05 <= args.opacity <= 1:
            ap.error("--opacity must be between 0.05 and 1")
    if args.seed is None:
        args.seed = int(time.time())
    if args.strokes is None:
        args.strokes = args.out.rsplit(".", 1)[0] + ".strokes.json"
    args.fn(args)


if __name__ == "__main__":
    main()
