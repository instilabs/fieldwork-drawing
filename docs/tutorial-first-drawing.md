# Tutorial: your first drawing in 10 minutes

By the end you will have a real drawing on the actual field:work platform,
made entirely from code, plus the app's own PNG export to prove it.

## 1. Install (2 min)

```bash
pip install playwright pillow numpy 'mcp<2'
python3 -m playwright install chromium  # installs the fallback / optional browser
```

Note the `'mcp<2'` pin: MCP 2.x renamed `FastMCP` and broke the API this
project uses. You only need the `mcp` package for the MCP server; the HTTP
API works without it.

## 2. Start the driver (1 min)

```bash
python3 fieldwork_server.py
```

Google Chrome opens on https://field-work-drawing.web.app/ by default, in a
fresh browser context rather than your everyday Chrome profile. If Chrome is
not installed, the server warns and falls back to Playwright Chromium. Choose
Chromium explicitly with `python3 fieldwork_server.py --browser chromium`; the
visible-browser behavior is identical. The API comes up on
`http://127.0.0.1:7766`. Check it:

```bash
curl 127.0.0.1:7766/health
# {"ok": true, "url": "https://field-work-drawing.web.app/", "format": "16:9", "page_size": [1920, 1080]}
```

Leave this running. Everything else talks to it.

## 3. Draw one stroke (1 min)

```bash
curl -X POST 127.0.0.1:7766/stroke -H 'Content-Type: application/json' \
  -d '{"points": [[300,700],[600,300],[900,700]], "ink": "#d53f2c", "size": 16}'
```

Look at the browser window: a red arc, drawn as a real pointer gesture. The
app cannot tell it came from code.

Coordinates are page units of the current format. 16:9 is 1920x1080. Change
format any time:

```bash
curl -X POST 127.0.0.1:7766/format -d '{"format": "4:5"}'   # 1080x1350
```

## 4. Look at your work (1 min)

```bash
curl -s 127.0.0.1:7766/screenshot -o canvas.png   # what's on screen now
curl -s 127.0.0.1:7766/png -o export.png          # the app's own PNG export
```

This is the feedback loop that fixes "agents draw badly": code can draw,
look, and correct.

## 5. Draw something real: replay a stroke list (5 min)

Single strokes are for control. Whole drawings are stroke lists. Generate one
with the bundled tracer on any photo:

```bash
python3 draw_with_code.py trace --photo your_photo.jpg --out sketch.png
curl -X POST 127.0.0.1:7766/replay -H 'Content-Type: application/json' \
  -d @sketch.strokes.json
```

`/replay` scales the list from its source resolution into the current page
format and executes every stroke as a gesture: about 700 strokes/sec flat
out, or add `"pace_ms": 30` to the body to watch it draw at human speed.

Undo the last stroke, or wipe the canvas and try again:

```bash
curl -X POST 127.0.0.1:7766/undo -d '{}'
curl -X POST 127.0.0.1:7766/clear -d '{}'
```

## Where next

- [Replay a photo trace](how-to-replay-photo-trace.md) for trace-mode knobs
  (density, edge threshold, shadows)
- [Replay decide-mode output](how-to-replay-decide-mode.md) for model-picked
  strokes
- [HTTP API reference](reference-http-api.md) for every endpoint
- [How the driver works](explanation-how-it-works.md) for what is really
  happening, and the honest limits
