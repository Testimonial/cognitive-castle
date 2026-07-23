# Claude Code Plugin

The recommended way to use Cognitive Castle with Claude Code — native marketplace install.

## Installation

```bash
claude plugin marketplace add Testimonial/cognitive-castle
claude plugin install --scope user castle
```

Restart Claude Code, then type `/skills` to verify "castle" appears.

## How It Works

With the plugin installed, Claude Code automatically:
- Starts the Cognitive Castle MCP server on launch
- Has access to all 29 tools
- Learns the AAAK dialect and memory protocol from the `castle_status` response
- Searches the palace before answering questions about past work

No manual configuration needed. Just ask:

> *"What did we decide about auth last month?"*

## Alternative: Manual MCP

If you prefer manual setup over the marketplace plugin:

```bash
claude mcp add castle -- python -m cognitive_castle.mcp_server
```

Both approaches give identical functionality. The plugin approach handles server lifecycle automatically.

## Hooks

Set up [auto-save hooks](/guide/hooks) to ensure memories are saved automatically during long conversations.
