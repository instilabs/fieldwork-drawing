# Reference: MCP tools

Exposed by `fieldwork_mcp.py` (FastMCP, `mcp<2`). The server wraps the HTTP
API, so `fieldwork_server.py` must be running first. All coordinates are
page units of the current format.

| Tool | Arguments | Returns |
|---|---|---|
| `fw_state()` | | Current tool, brush, format (text) |
| `fw_format(format)` | `1:1`, `4:5`, `5:4`, `9:16`, `16:9` | Confirmation |
| `fw_tool(tool)` | `draw`, `paint`, `boids`, `erase` | Confirmation |
| `fw_brush(ink?, size?, opacity?)` | any subset | Confirmation |
| `fw_stroke(points, ink?, size?, opacity?)` | `points: [[x,y],...]` | Draws one stroke |
| `fw_paint(points, shape?, ink?, size?)` | shape default `o` | Stamp-scrub an area |
| `fw_boids(points, heading?, speed?, curl?, shape?)` | heading default 90, speed 100 | Release a flock |
| `fw_erase(points, size?)` | size default 40 | Erase along a path |
| `fw_replay(strokes, source_size?, clear_first?, pace_ms?)` | same schema as `POST /replay` | Replays a stroke list |
| `fw_undo()` | | Undo last stroke |
| `fw_clear()` | | Clear canvas |
| `fw_screenshot()` | | Image of the live canvas |
| `fw_export_png()` | | Image: the app's own PNG export |

`fw_screenshot` and `fw_export_png` return MCP `Image` content, so a vision
-capable agent can see the result of its own drawing and iterate.
