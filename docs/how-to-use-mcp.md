# How to connect the MCP server to your local AI tools

`fieldwork_mcp.py` exposes the drawing driver as 13 MCP tools, so an agent can
draw on the real platform and see its own work.

## Prerequisites

1. Start the HTTP API in a terminal: `python3 fieldwork_server.py`. It opens
a visible browser and listens on `http://127.0.0.1:7766` (Chrome by default;
falls back to Playwright Chromium if Chrome is not installed).
2. Install the MCP dependency: `pip install 'mcp<2'`. MCP 2.x renamed
`FastMCP` and broke the API this project uses.
3. In the examples below, replace `/absolute/path/to/fieldwork_mcp.py` with
the full path to this repository's `fieldwork_mcp.py`.

## Antigravity

Antigravity reads local stdio MCP servers from `mcp_config.json`. For a global
setup, edit `~/.gemini/config/mcp_config.json`. For a workspace-only setup,
use `.agents/mcp_config.json` in the project.

Add this entry to the file (merge it into an existing `mcpServers` object if
one is already present):

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

In Antigravity CLI, open the MCP manager with `/mcp` to check the server
status. In the IDE, use the MCP Servers / Manage MCP Servers controls to
reload or inspect it.

## Codex

Add the local stdio server with the Codex CLI:

```bash
codex mcp add fieldwork -- python3 /absolute/path/to/fieldwork_mcp.py
codex mcp list
```

Or add the same server directly to `~/.codex/config.toml`:

```toml
[mcp_servers.fieldwork]
command = "python3"
args = ["/absolute/path/to/fieldwork_mcp.py"]
```

Codex CLI and its IDE extension share this configuration. In the Codex TUI,
`/mcp` shows the connected servers.

## Claude Code

Register it as a local stdio server:

```bash
claude mcp add --transport stdio fieldwork -- python3 /absolute/path/to/fieldwork_mcp.py
claude mcp list
```

The `--` separates Claude Code's options from the command that starts the
server. In a Claude Code session, `/mcp` shows its status.

## Other MCP clients

Other clients that support local stdio MCP servers can use the same
`command` and `args` shown above, in the location and format their docs specify.

## The see-your-own-work loop

The two tools that matter most:

- `fw_screenshot` returns the live canvas as an image. The agent can look at
  what it just drew and correct the next strokes.
- `fw_export_png` returns the app's own PNG export.

A good agent loop: draw a few strokes, call `fw_screenshot`, compare with the
intent, adjust, and repeat. The agent can now inspect the actual canvas rather
than guessing whether its drawing worked.

Quick sanity check from any MCP client: call `fw_state` (should report the
current tool, brush and format), then `fw_stroke` with a short point list,
then `fw_screenshot` to see it.

Full signatures: [MCP tools reference](reference-mcp-tools.md).

## Official client references

- [Antigravity MCP configuration](https://antigravity.google/docs/mcp/)
- [Codex MCP setup and config.toml](https://developers.openai.com/codex/extend/mcp)
- [Claude Code MCP setup](https://code.claude.com/docs/en/mcp)
