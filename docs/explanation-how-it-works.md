# Explanation: how the driver works, and its limits

## Why pointer gestures instead of an API

The field:work app is a closed, local-only p5.js instance-mode app. There is
no websocket, no network sync, no import/export API, no URL parameters, no
console hooks. Its state lives in localStorage and its input lives on an
overlay canvas element (`#live`) that listens for standard pointer events.

So the only way in is the front door: be a hand. The driver opens the real app
in installed Google Chrome by default and feeds it pointer gestures at canvas
coordinates. If Chrome is missing, it warns and falls back to bundled
Playwright Chromium; select it directly with `python fieldwork_server.py --browser chromium`.
Both options show the same visible app. Playwright creates a fresh browser
context either way, not a connection to your everyday Chrome profile.
Everything downstream (the living system presets, Paint stamps, Boids, PNG
export, video recording) then behaves exactly as it does for a human, because
as far as the app knows, this is a human.

## Python environment

Use a project-local `.venv` with the dependencies from `requirements.txt`.
The [README Quick start](../README.md#quick-start) shows the recommended uv
setup and the classic `venv`/pip alternative. Run Python commands with this
environment active. To install Playwright's bundled Chromium fallback, run
this from the active `.venv`:

```bash
python -m playwright install chromium
```

## The two input paths

- **Trusted CDP mouse** for single strokes (`/stroke`): real
  `mouse.move/down/up` through Playwright. Highest fidelity, about 30ms per
  stroke.
- **Batched synthetic PointerEvents** for replays (`/replay`): strokes are
  dispatched directly at `#live` inside one `page.evaluate` call, 500 per
  chunk. The app does not check `isTrusted` and it catches
  `setPointerCapture` failures, so synthetic events are equivalent, and this
  is roughly 700 strokes/sec, which is what makes multi-thousand-stroke
  replays practical for live use.

## Coordinates

Callers work in page units (the app's format resolution, e.g. 1920x1080 for
16:9). The driver maps them to screen pixels using the app's own view
transform, captured by wrapping `ctx.setTransform` at startup rather than
reimplementing the view math. If the app changes its transform code, the hook
still follows it.

UI controls (tool, format, ink, size, opacity) are the app's own `data-bind`
DOM controls, set through Playwright clicks and input events, so they go
through the app's normal change handling.

## Honest limits

- **No flood fill.** The app has none, so flat color regions are dense
  parallel scanline strokes (`replicate.py`). From arm's length they read as
  solid; up close they have a printed texture. Lean into it.
- **Boids are alive.** Scripts place the area and set heading/speed/curl;
  after release the system animates the flock on its own. You cannot
  choreograph it.
- **Pressure is constant 0.5.** The app only reads pressure from real pens;
  mouse input is a constant. Line width comes from brush size set per stroke,
  visually equivalent but not per-point.
- **System presets move lines.** New lines default to Held (they stay put).
  Pick Breathing/Restless/etc. in the panel and your marks will drift on
  purpose; the global Strength slider scales it.
- **Replay speed** tops out around 700 strokes/sec. Use `pace_ms` for drama.
- **Screenshots settle 0.4s** so the 15fps canvas paints before capture.
- **The app is a PWA.** Load it once on good wifi and it keeps working
  offline; the driver itself only needs localhost.
