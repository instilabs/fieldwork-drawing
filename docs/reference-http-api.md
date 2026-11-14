# Reference: HTTP API

Served by `fieldwork_server.py` on `http://127.0.0.1:7766` (override with
`--port`; `--headless` hides the browser window). All POST endpoints take a
JSON body. Coordinates are page units of the current format.

Page formats: `1:1` (1080x1080), `4:5` (1080x1350), `5:4` (1350x1080),
`9:16` (1080x1920), `16:9` (1920x1080).

## Reads

| Endpoint | Returns |
|---|---|
| `GET /health` | `{ok, url, format, page_size}` |
| `GET /state` | `{tool, format, ink, size, opacity, eraser_size, paper, preset, boid_preset}` current app state |
| `GET /png` | `image/png` - the app's own PNG export, full page resolution |
| `GET /screenshot` | `image/png` - the live screen (settles 0.4s so the 15fps canvas paints) |

## Controls

| Endpoint | Body | Effect |
|---|---|---|
| `POST /format` | `{"format": "4:5"}` | Set page format |
| `POST /tool` | `{"tool": "draw"}` | `draw`, `paint`, `boids`, `erase` |
| `POST /preset` | `{"preset": "breathing", "kind": "system"}` | Living preset: `held` `breathing` `restless` `wandering` `nervous` `melting` `frozen` `custom`. With `"kind": "boid"`: `stream` `drizzle` `crowd` `crawl` `rush` `scatter` `custom` |
| `POST /brush` | `{"ink": "#d53f2c", "size": 14, "opacity": 0.9}` | Any subset |
| `POST /undo` | `{}` | Undo last stroke |
| `POST /clear` | `{}` | Clear canvas (with confirm) |

## Drawing

| Endpoint | Body | Effect |
|---|---|---|
| `POST /stroke` | `{"points": [[x,y],...], "ink"?, "size"?, "opacity"?, "tool"?, "pace_ms"?}` | One stroke. `[[x,y]]` (single point) = dot |
| `POST /paint` | `{"points": [[x,y],...], "shape"?, "ink"?, "size"?}` | Scrub an area with stamp fill (shapes: `o x + square diamond`) |
| `POST /boids` | `{"points": [[x,y],...], "heading"?, "speed"?, "curl"?, "shape"?, "ink"?, "size"?}` | Release a flock over an area |
| `POST /erase` | `{"points": [[x,y],...], "size"?}` | Erase along a path |
| `POST /replay` | see below | Replay a whole stroke list |

## POST /replay

```json
{
  "strokes": [{"points": [[x, y], ...], "color": "#rrggbb", "width": 3}],
  "source_size": [1000, 1400],
  "clear_first": false,
  "pace_ms": 6,
  "max_strokes": null,
  "width_scale": 1.0,
  "opacity": null,
  "preset": null
}
```

- Each stroke: `points` (required), `color` or `ink` (default `#1a1a1a`),
  `width` in px (default 3), plus optional technique keys:
  - `tool`: `draw` (default), `paint`, `boids` or `erase`
  - `opacity`: 0.05-1 (overrides the top-level `opacity` default)
  - `preset`: living system preset applied just before that stroke's group
  - `shape`: paint stamp (`o` `x` `+` `square` `diamond`) or boid shape
    (`dot` `arrow` `chevron` `dash`), matching the stroke's `tool`
  - `boid_preset`: `stream` `drizzle` `crowd` `crawl` `rush` `scatter`
  - `boid_heading`, `boid_speed`, `boid_curl`, `boid_variety`, `boid_density`
  - `eraser_size`: 4-200, for `erase` strokes (default: the stroke's width)
- Top-level `preset`: set the living system preset once before drawing
  (e.g. `"breathing"`). It animates the whole canvas, strokes already drawn
  included, until changed.
- `source_size`: the coordinate space of the list. The replay scales it
  uniformly into the current page format and centers it. Omit to use the
  list's own bounding box.
- Consecutive strokes with identical settings are grouped; each group's
  settings are pushed only where they differ from the previous group,
  and strokes are dispatched as synthetic pointer events inside the
  page, one chunk at a time. Measured: a 7,572-stroke replay with
  per-stroke color/width changes lands in about 18 seconds (the old
  round-trip-per-change path needed over a minute per 2,000 strokes);
  well-grouped scanline fills run ~2,200 strokes/sec. The app's own
  renderer is the floor - it slows as ink accumulates. Paint strokes land
  ~90 stamp shapes each and the app slows as shapes accumulate (tens of
  strokes/sec at first, single digits past a few hundred strokes) - keep
  paint/boids replays small.
- Response: `{"replayed": N, "seconds": S, "page": [w,h], "scale": k}`.

This is exactly the format `draw_with_code.py` writes to
`<out>.strokes.json`, so decide and trace outputs replay directly.
