# Reference: features, end to end

Everything fieldwork-drawing does, in one pass. Each section links to the
focused doc for its topic; this page is the map.

## Install and environment

Dependencies (`requirements.txt`): `playwright`, `pillow`, `numpy`, `scipy`,
`mcp<2`. Create a project `.venv` and install them with uv (recommended) or
classic `venv` + `pip` - both flows are in the
[README quick start](../README.md#quick-start). Install the bundled Chromium
fallback with `python -m playwright install chromium` from the active
`.venv`. The `mcp` package is only needed for the MCP server; the HTTP API
works without it.

## Browsers

Every entry point (server, `--live`, `replicate.py --run`) launches installed
Google Chrome by default in a fresh browser context - not your everyday
Chrome profile. If Chrome is missing, it warns and falls back to Playwright's
bundled Chromium. Pick one explicitly with `--browser chrome|chromium`.
`--headless` hides the window for testing.

## The three ways in

1. **HTTP API** - `python fieldwork_server.py`, then talk to
   `http://127.0.0.1:7766` from any language. Best for scripts and demos.
2. **MCP server** - `python fieldwork_mcp.py` wraps the HTTP API as 13 MCP
   tools, so an agent (Antigravity, Codex, Claude Code, ...) can draw and
   screenshot its own work. Setup: [How to use the MCP server](how-to-use-mcp.md).
3. **Direct import** - `from fieldwork_server import BrowserDriver,
   act_replay, ...` drives the app in-process. This is what
   `replicate.py --run` and `draw_with_code.py --live` use.

## trace mode: photo to ink sketch

```bash
python3 draw_with_code.py trace --photo model.jpg --out sketch.png
```

Writes `sketch.png` (a PIL preview) and `sketch.strokes.json` (the replayable
stroke list). Deterministic edge-following contour strokes plus shadow
hatching; `--seed` fixes the jitter.

| Flag | Default | Effect |
|---|---|---|
| `--photo` | (required) | Source photo |
| `--out` | `sketch.png` | Preview PNG |
| `--size WxH` | `1000x1400` | Working resolution |
| `--style` | none | One of the six artist styles below |
| `--edge-pct` | 6.0 | Percent of pixels treated as contour (2-12) |
| `--max-strokes` | 9000 | Cap on contour strokes |
| `--density` | 1.0 | Stroke density multiplier |
| `--shadow-level` | 0.55 | Gray level below which hatching appears |
| `--seed` | time | Reproducible jitter |
| `--strokes` | `<out>.strokes.json` | Stroke-list output path |
| `--color` | off | Sample the photo's colors per stroke instead of grayscale ink |
| `--tool` | `draw` | Replay with `draw`, `paint` (stamps) or `boids` (flocks) |
| `--paint-shape` | none | Stamp shape: `o x + square diamond` (needs `--tool paint`) |
| `--boid-shape` | none | Boid shape: `dot arrow chevron dash` (needs `--tool boids`) |
| `--boid-preset` | none | Flock behavior: `stream drizzle crowd crawl rush scatter` |
| `--opacity` | none | Brush opacity 0.05-1 for every stroke (app replay only) |
| `--preset` | none | Living system preset for the replay: `held breathing restless wandering nervous melting frozen` |
| `--codegen OUT.py` | none | Also write a standalone redraw script that replays through the local API |
| `--pace-ms` | 0 | ms between strokes inside the `--codegen` script |

Technique flags (`--tool`, `--opacity`, shapes, `--boid-preset`) ride along
inside the stroke file, so they work identically for `/replay`, `--live`
and `--codegen` scripts. Explicit flags always win over a `--style` bundle;
`--color` overrides the style's ink.

## The six trace styles

`--style` bundles tool/preset/opacity/ink/paper and generation knobs into a
tuned look:

| Style | Look |
|---|---|
| `gesture` | Few bold strokes, big brush, nervous preset - a 2-minute live-model sketch |
| `ink-wash` | Soft grays, low-opacity layered strokes, breathing preset - moody, good for portraits |
| `stipple` | Dots with density mapped to shading - pointillism (single-point draw strokes) |
| `blueprint` | White ink on dark blue paper, ruler-straight, frozen preset - technical drawing |
| `swarm` | The sketch drawn by a boid flock, wandering preset - chaotic but alive; demo showpiece |
| `field-notes` | Sepia ink, slightly restless, sketchy double-lines - Da Vinci notebook energy |

The paint/boids styles cap their stroke counts low on purpose (see caveats);
raise them with explicit `--max-strokes` only if you enjoy slideshows. Details:
[Replay a photo trace](how-to-replay-photo-trace.md).

## decide mode: a model picks every mark

```bash
python3 draw_with_code.py decide --mood "seated model, flowing ink" --steps 400
```

Asks a local ollaya decision model (`POST /v1/systemone`) for each mark -
shape, direction, length, color, pressure, pen-lift - and renders them.
"It decides, it doesn't generate." If the daemon is down it falls back to a
seeded random chooser, so the demo never dies. Writes `drawing.png` and
`drawing.strokes.json`, re-rendered every `--save-every` steps.

| Flag | Default | Effect |
|---|---|---|
| `--model` | `laya:en` | Ollaya model that picks each stroke |
| `--api-base` | `http://127.0.0.1:11435` | Ollaya daemon |
| `--mood` | seated pose, flowing ink | Prompt steering the picks |
| `--steps` | 400 | Number of model decisions |
| `--size WxH` | `1000x1400` | Working resolution |
| `--scale` | 1.0 | Stroke length multiplier |
| `--seed` | time | Reproducible output |
| `--save-every` | 20 | Redraw the preview every N steps |
| `--out` | `drawing.png` | Preview PNG |
| `--strokes` | `<out>.strokes.json` | Stroke-list output path |

Details: [Replay decide-mode output](how-to-replay-decide-mode.md).

## --live: draw on the real app while you watch

Both modes share the same `--live` code path: after the PNG and strokes file
are written, the app opens in a browser window and the strokes are drawn on
it at a watchable pace. The window stays open when finished; press Enter in
the terminal to close it.

```bash
python3 draw_with_code.py trace --photo pose.jpg --live --speed 20
python3 draw_with_code.py decide --steps 200 --live --speed 20
```

| Flag | Default | Effect |
|---|---|---|
| `--live` | off | Draw on the live app after generating |
| `--speed` | 30 | Live draw speed, strokes per second (0 = as fast as the app goes) |
| `--format` | leave as-is | Set the app's page format first (`1:1 4:5 5:4 9:16 16:9`) |
| `--clear` | off | Wipe the canvas before drawing |
| `--browser` | `chrome` | `chrome` or bundled `chromium` |
| `--headless` | off | No visible window (for testing) |

## HTTP API

Served on `http://127.0.0.1:7766` (`--port` to change, `--headless` to hide
the window). Exact shapes: [HTTP API reference](reference-http-api.md).

- Reads: `GET /health`, `GET /state` (current tool, brush, format, presets),
  `GET /png` (the app's own export), `GET /screenshot` (what's on screen).
- Controls: `POST /format`, `POST /tool`, `POST /brush`, `POST /preset`
  (living system presets, or boid presets with `"kind": "boid"`),
  `POST /undo`, `POST /clear`.
- Drawing: `POST /stroke`, `POST /paint`, `POST /boids`, `POST /erase`, and
  `POST /replay` for whole stroke lists.
- `/replay` takes `{strokes, source_size?, clear_first?, pace_ms?,
  max_strokes?, width_scale?, opacity?, preset?, paper?}`. Each stroke can
  carry technique keys (`tool`, `opacity`, `preset`, `shape`, `boid_*`,
  `eraser_size`). `paper` sets the page background once first; `preset`
  animates the whole canvas. Consecutive strokes with identical settings
  are grouped, each group's settings are pushed only where they differ from
  the previous group, and strokes are dispatched inside the page - a
  7,572-stroke decide-mode replay with per-stroke color/width changes lands
  in about 18 seconds (the old round-trip-per-stroke path needed over a
  minute per 2,000). `pace_ms` slows it to a watchable speed.

## MCP server: 13 tools

`fieldwork_mcp.py` (stdio): `fw_state`, `fw_format`, `fw_tool`, `fw_brush`,
`fw_stroke`, `fw_paint`, `fw_boids`, `fw_erase`, `fw_replay`, `fw_undo`,
`fw_clear`, `fw_screenshot`, `fw_export_png`. The screenshot/export tools are
the feedback loop: the agent draws, looks, and corrects. Signatures:
[MCP tools reference](reference-mcp-tools.md).

## replicate.py: the benchmark

`replicate.py` rebuilds a reference drawing: color-region masks become dense
scanline fills (the app has no flood fill), outlines come from trace mode and
draw last, on top - exactly how the original was inked.

```bash
python3 replicate.py --build --photo reference.jpg --lines ref_lines.strokes.json
python3 replicate.py --run   --photo reference.jpg --lines ref_lines.strokes.json
```

`--run` builds, switches the app to `--format` (default 16:9, landscape like
the original reference), replays at full speed, and saves the app's PNG
export to `--export` (default `replica_export.png`); `--show` watches it in
a visible window. The README banner image is this pipeline's output: 3,812
strokes in 5.7 seconds on the real platform.

## Sample photo and credits

`sample-pose.jpg` - breakdance one-hand freeze, photo by
[Niko Twisty on Pexels](https://www.pexels.com/photo/a-man-breakdancing-on-the-street-13993424/).
Free to use under the Pexels license; attribution not required. Bundled so
trace mode works out of the box.

`sample_photos/` holds the photos from the field:work "Drawing with code"
session (jo+kapi, 14 Nov 2026; live model Sonia Kwek), and `sample_redraws/`
the replayable redraw scripts generated from them with `trace --codegen` -
see its README for the script-to-photo mapping.

## Known caveats

- **No flood fill.** Flat color regions are dense parallel scanline strokes
  (`replicate.py`). From arm's length they read as solid; up close they have
  a printed texture.
- **Paint and boids get slow as marks accumulate.** A Paint stroke lands ~90
  stamp shapes, and the app slows superlinearly past a few hundred shapes
  (tens of strokes/sec at first, single digits later). The `stipple` and
  `swarm` styles cap their counts low for this reason.
- **Presets are canvas-wide.** A living system preset animates every stroke
  on the page, drawn before or after it was picked - a per-stroke `preset`
  key sets the canvas preset just before that stroke's group, it does not
  scope the animation to those strokes.
- **Boids are alive.** Scripts place the area and set heading/speed/curl;
  after release the system animates the flock on its own. You cannot
  choreograph it. `POST /clear` wipes lines, shapes and live boids alike
  (verified on app v0.10.0).
- **Letterboxing.** `/replay` scales the stroke list uniformly into the
  current page format and centers it; when the aspect ratios differ you get
  empty bands. Match `--format` to your source aspect to fill the page.
- **Pressure is constant 0.5.** The app only reads pressure from real pens;
  line weight comes from brush size set per stroke, visually equivalent but
  not per-point.
- **Replay speed has a floor: the app itself.** Dispatch is effectively
  instant, but the app's own renderer slows as ink accumulates, so a full
  7k-stroke drawing takes seconds, not milliseconds, however you send it.
- **The app is a PWA.** Load it once on good wifi and it keeps working
  offline; the driver only needs localhost.
