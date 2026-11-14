# fieldwork-drawing

Draw with code on the real [field:work](https://field-work-drawing.web.app/) event platform.

A Playwright driver plays the app's canvas like an instrument: strokes go in
as genuine pointer gestures, so everything the platform does for a human (the
living system presets, Paint stamps, Boids, PNG export) works for code too. It
uses installed Google Chrome by default, with a fresh browser context rather
than your everyday Chrome profile; if Chrome is missing, it warns and falls
back to Playwright Chromium.
On top of the driver sit two ways in:

- **HTTP API** (`fieldwork_server.py`, `127.0.0.1:7766`) - call it from any
  script, any language.
- **MCP server** (`fieldwork_mcp.py`, 13 tools) - connect local MCP clients
  such as Antigravity, Codex, and Claude Code straight to the canvas.

![A reference image replicated on the real platform by replicate.py: 3812 strokes in 5.7 seconds](docs/images/replica_export.png)

*Above: a reference drawing replicated on the actual platform (the app's own
PNG export). 3,812 strokes in 5.7 seconds.*

## Quick start

Create a project `.venv` and install the dependencies. **Option A (recommended): uv**

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

`uv` works without system Python. If it cannot find an interpreter, it downloads
a standalone Python into its managed data directory (by default,
`~/.local/share/uv/python`). This does not replace system Python or add Python
to your `PATH`. To use a conda interpreter instead, activate that conda
environment first, then create the project venv with:

```bash
uv venv --python "$(which python)"
```

After installing, run without activating `.venv` with
`uv run --no-project python fieldwork_server.py` from the repo root.

**Option B: classic `venv` and `pip`**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

With either option, install the bundled Chromium fallback from the active
`.venv` if you need it:

```bash
python -m playwright install chromium
```

Start the driver from the repo root with `.venv` active:

```bash
python fieldwork_server.py             # Chrome by default; API on 127.0.0.1:7766
python fieldwork_server.py --browser chromium  # explicitly use bundled Chromium
```

Draw a line from any code:

```bash
curl -X POST 127.0.0.1:7766/stroke -H 'Content-Type: application/json' \
  -d '{"points": [[200,200],[500,400],[900,300]], "ink": "#d53f2c", "size": 14}'
```

Chrome must be installed to use the default browser. If it is not available,
the server warns and falls back to the bundled Chromium installed above. The
visible-browser behavior is the same either way.

Then follow the [tutorial](docs/tutorial-first-drawing.md) to produce a full
drawing in about ten minutes.

## Docs (Diataxis layout)

| Kind | Doc | Use it when |
|---|---|---|
| Tutorial | [Your first drawing in 10 minutes](docs/tutorial-first-drawing.md) | Learning the system end to end |
| How-to | [Replay a photo trace onto the app](docs/how-to-replay-photo-trace.md) | Photo to ink sketch on the platform |
| How-to | [Replay ollaya decide-mode output](docs/how-to-replay-decide-mode.md) | Model-picked strokes on the platform |
| How-to | [Hook the MCP server to Antigravity, Codex, or Claude Code](docs/how-to-use-mcp.md) | Let an agent draw and see its work |
| Reference | [HTTP API](docs/reference-http-api.md) | Exact endpoint shapes |
| Reference | [Features, end to end](docs/reference-features.md) | Every mode, flag, endpoint and caveat in one pass |
| Reference | [MCP tools](docs/reference-mcp-tools.md) | Exact tool signatures |
| Explanation | [How the driver works, and its limits](docs/explanation-how-it-works.md) | Why synthetic gestures, honest limits |

## The event demo

```bash
# terminal 1 (Chrome by default; add --browser chromium to choose bundled Chromium)
python3 fieldwork_server.py

# terminal 2: generate a stroke list AND replay it onto the real app
python3 draw_with_code.py decide --mood "seated model, flowing ink, confident" --steps 400
curl -X POST 127.0.0.1:7766/replay -H 'Content-Type: application/json' -d @drawing.strokes.json
# (or skip the curl: decide --live draws straight onto the app, stroke by stroke)

# photo of the model -> ink sketch strokes -> real platform
python3 draw_with_code.py trace --photo sample-pose.jpg --out pose_sketch.png
curl -X POST 127.0.0.1:7766/replay -H 'Content-Type: application/json' -d @pose_sketch.strokes.json

# or pick a curated artist style (gesture, ink-wash, stipple, blueprint,
# swarm, field-notes) - one flag bundles tool, ink, preset and density knobs
python3 draw_with_code.py trace --photo sample-pose.jpg --style blueprint --live
```

Add `"pace_ms": 30` to the replay body to watch it draw at human speed.

Or skip the server entirely: `trace --live` opens the app in a browser window
and draws the sketch stroke by stroke, like a hand drawing:

```bash
python3 draw_with_code.py trace --photo pose.jpg --live --speed 20
# --speed is strokes per second (default 30); --clear wipes the canvas first,
# --format 4:5 sets the page format, --headless hides the window

# and the sketch is not stuck as pencil: use the platform's own tools and
# living presets (they ride along in the stroke file and --codegen scripts)
python3 draw_with_code.py trace --photo pose.jpg \
  --tool paint --paint-shape o --opacity 0.5 --preset breathing --live
python3 draw_with_code.py trace --photo pose.jpg \
  --tool boids --boid-preset drizzle --live
```

Venue wifi tip: the app is a PWA with a service worker. Load it once on good
wifi and it keeps working offline; the driver only needs localhost.

## Files

- `fieldwork_server.py` - browser driver + HTTP API (the core)
- `fieldwork_mcp.py` - MCP wrapper (13 tools)
- `draw_with_code.py` - decide (ollaya `/v1/systemone`) + trace (photo to
  strokes); both also write `.strokes.json` for replay, and trace can draw
  straight onto the live app with `--live`. `--tool paint|boids`, `--opacity`
  and `--preset breathing|nervous|...` put the platform's Paint stamps, Boids
  flocks and living system presets into the stroke file, and `--style` bundles
  a whole tuned look (six artist styles) behind one flag
- `replicate.py` - reference-image replication pipeline (the benchmark above)
- `docs/reference-features.md` - the full feature rundown: every mode,
  flag, endpoint and caveat in one place
- `sample-pose.jpg` - free sample photo (Pexels) so trace mode works out of
  the box - see Credits

More samples: [decide mode](docs/images/decide-mode.png),
[trace mode](docs/images/trace-mode.png),
[benchmark line pass](docs/images/benchmark-line-pass.png).

## Credits

- `sample-pose.jpg` - breakdance one-hand freeze, photo by
  [Niko Twisty on Pexels](https://www.pexels.com/photo/a-man-breakdancing-on-the-street-13993424/).
  Free to use under the Pexels license; attribution not required.
