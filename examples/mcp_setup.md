# MCP Integration — Claude Code

## Setup

Run the MCP server:

```bash
castle-mcp
```

Or add it to Claude Code:

```bash
claude mcp add castle -- castle-mcp
```

## Available Tools

The server exposes the full Cognitive Castle MCP toolset. Common entry points include:

- **castle_status** — palace stats (wings, rooms, drawer counts)
- **castle_search** — semantic search across all memories
- **castle_list_wings** — list all projects in the palace

## Usage in Claude Code

Once configured, Claude Code can search your memories directly during conversations.
