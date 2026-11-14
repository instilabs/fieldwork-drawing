#!/usr/bin/env python3
"""
fieldwork_mcp.py - MCP server for the field:work drawing app.

Wraps fieldwork_server.py's HTTP API (start that first) so any MCP client -
Claude Desktop, Cursor, your own agent - can draw on the real platform:

  1. python3 fieldwork_server.py          # browser + http://127.0.0.1:7766
  2. python3 fieldwork_mcp.py             # stdio MCP server (this file)

Claude Desktop config (claude_desktop_config.json):
  {
    "mcpServers": {
      "fieldwork": {
        "command": "python3",
        "args": ["/path/to/fieldwork_mcp.py"]
      }
    }
  }

Coordinates are PAGE units of the app's current format (e.g. 1920x1080 for
16:9). Use fw_screenshot to see the canvas after drawing - the feedback loop
that keeps an agent's drawing honest.
"""

import json
import os
import urllib.request

from mcp.server.fastmcp import FastMCP, Image

API = os.environ.get("FIELDWORK_API", "http://127.0.0.1:7766")

mcp = FastMCP("fieldwork", instructions=(
    "Drive the field:work 'Drawing with Code' web app through real pointer "
    "input. Coordinates are page units of the current format (check "
    "fw_state for page_size). Typical loop: fw_stroke / fw_replay to draw, "
    "fw_screenshot to look, adjust, repeat."
))


def _get(path):
    with urllib.request.urlopen(API + path, timeout=30) as r:
        return r.read()


def _post(path, payload, timeout=600):
    req = urllib.request.Request(
        API + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


@mcp.tool()
def fw_state() -> str:
    """Current tool, brush (ink/size/opacity), format and page size."""
    state = json.loads(_get("/state").decode())
    health = json.loads(_get("/health").decode())
    state["page_size"] = health.get("page_size")
    return json.dumps(state)


@mcp.tool()
def fw_format(format: str) -> str:
    """Set the canvas format: '1:1' (1080x1080), '4:5' (1080x1350),
    '5:4' (1350x1080), '9:16' (1080x1920) or '16:9' (1920x1080)."""
    return json.dumps(_post("/format", {"format": format}))


@mcp.tool()
def fw_tool(tool: str) -> str:
    """Select the tool: 'draw' (lines), 'paint' (stamp fills), 'boids'
    (animated flock stream) or 'erase'."""
    return json.dumps(_post("/tool", {"tool": tool}))


@mcp.tool()
def fw_brush(ink: str = None, size: int = None, opacity: float = None) -> str:
    """Set brush color (hex like '#1a1a1a'), size (1-60 px line width at
    medium pressure) and/or opacity (0.05-1). Only passed fields change."""
    body = {k: v for k, v in {"ink": ink, "size": size, "opacity": opacity}.items()
            if v is not None}
    return json.dumps(_post("/brush", body))


@mcp.tool()
def fw_stroke(points: list, ink: str = None, size: int = None,
              opacity: float = None) -> str:
    """Draw one stroke through points [[x, y], ...] in page units. Two points
    make a straight line; more points make a flowing curve. A single point
    draws a dot of diameter `size`. Optionally set ink/size/opacity first."""
    body = {"points": points}
    if ink is not None:
        body["ink"] = ink
    if size is not None:
        body["size"] = size
    if opacity is not None:
        body["opacity"] = opacity
    return json.dumps(_post("/stroke", body))


@mcp.tool()
def fw_paint(points: list, shape: str = "o", ink: str = None,
             size: int = None) -> str:
    """Scrub an area with the Paint tool (fills it with a stamp pattern).
    points trace the area to cover. shape: o, x, +, square or diamond."""
    body = {"points": points, "shape": shape}
    if ink is not None:
        body["ink"] = ink
    if size is not None:
        body["size"] = size
    return json.dumps(_post("/paint", body))


@mcp.tool()
def fw_boids(points: list, heading: int = 90, speed: int = 100,
             curl: int = 70, shape: str = "dot") -> str:
    """Release an animated boid flock over the area traced by points.
    heading: degrees clockwise from up (90 = right). The flock keeps moving
    on its own - scripts place it, the system animates it."""
    return json.dumps(_post("/boids", {"points": points, "heading": heading,
                                       "speed": speed, "curl": curl,
                                       "shape": shape}))


@mcp.tool()
def fw_erase(points: list, size: int = 40) -> str:
    """Erase along the path through points. size is the eraser diameter."""
    return json.dumps(_post("/erase", {"points": points, "size": size}))


@mcp.tool()
def fw_replay(strokes: list, source_size: list = None, clear_first: bool = False,
              pace_ms: int = 0, width_scale: float = 1.0) -> str:
    """Replay a whole drawing: a list of strokes, each
    {"points": [[x, y], ...], "color": "#rrggbb", "width": px}.
    source_size [w, h] scales them into the page (defaults to the largest
    coordinate). pace_ms adds a delay between strokes for live watching."""
    body = {"strokes": strokes, "clear_first": clear_first,
            "pace_ms": pace_ms, "width_scale": width_scale}
    if source_size:
        body["source_size"] = source_size
    return json.dumps(_post("/replay", body))


@mcp.tool()
def fw_undo() -> str:
    """Undo the last mark."""
    return json.dumps(_post("/undo", {}))


@mcp.tool()
def fw_clear() -> str:
    """Clear the whole drawing."""
    return json.dumps(_post("/clear", {}))


@mcp.tool()
def fw_screenshot() -> Image:
    """PNG of the canvas as it looks right now. Look at your work."""
    return Image(data=_get("/screenshot"), format="png")


@mcp.tool()
def fw_export_png() -> Image:
    """The app's own PNG export at full page resolution."""
    return Image(data=_get("/png"), format="png")


if __name__ == "__main__":
    mcp.run()
