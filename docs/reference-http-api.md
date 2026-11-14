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
| `GET /state` | `{tool, brush, format, ...}` current app state |
| `GET /png` | `image/png` - the app's own PNG export, full page resolution |
| `GET /screenshot` | `image/png` - the live screen (settles 0.4s so the 15fps canvas paints) |

## Controls

| Endpoint | Body | Effect |
|---|---|---|
| `POST /format` | `{"format": "4:5"}` | Set page format |
| `POST /tool` | `{"tool": "draw"}` | `draw`, `paint`, `boids`, `erase` |
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
  "opacity": null
}
```

- Each stroke: `points` (required), `color` or `ink` (default `#1a1a1a`),
  `width` in px (default 3).
- `source_size`: the coordinate space of the list. The replay scales it
  uniformly into the current page format and centers it. Omit to use the
  list's own bounding box.
- Consecutive strokes with the same color and size are grouped, so brush
  changes (DOM round trips) happen once per group. Throughput is about
  700 strokes/sec at `pace_ms: 0`.
- Response: `{"replayed": N, "seconds": S, "page": [w,h], "scale": k}`.

This is exactly the format `draw_with_code.py` writes to
`<out>.strokes.json`, so decide and trace outputs replay directly.
