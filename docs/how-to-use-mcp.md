# How to hook the MCP server to Claude Desktop or Cursor

`fieldwork_mcp.py` exposes the whole driver as 13 MCP tools, so an agent can
draw on the real platform and see its own work.

## Prerequisites

- The HTTP API running: `python3 fieldwork_server.py` (the MCP server is a
  thin wrapper over it)
- `pip install 'mcp<2'` (MCP 2.x renamed `FastMCP` and broke the API)

## Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "fieldwork": {
      "command": "python3",
      "args": ["/absolute/path/to/fieldwork_mcp.py"]
    }
  }
}
```

Restart Claude Desktop. The `fw_*` tools appear in the tool list.

## Cursor

Add the same block under `mcpServers` in your Cursor MCP settings
(`.cursor/mcp.json` or global config).

## The see-your-own-work loop

The two tools that matter most:

- `fw_screenshot` returns the live canvas as an image. The agent can look at
  what it just drew and correct the next strokes.
- `fw_export_png` returns the app's own PNG export.

A good agent loop: draw a few strokes, `fw_screenshot`, compare with the
intent, adjust, repeat. This is the fix for "the agent's drawing skills are
quite bad": the skills stay the same, but now there is feedback.

Quick sanity check from any MCP client: call `fw_state` (should report the
current tool, brush and format), then `fw_stroke` with a short point list,
then `fw_screenshot` to see it.

Full signatures: [MCP tools reference](reference-mcp-tools.md).
