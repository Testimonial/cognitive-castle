# MCP Integration

Cognitive Castle provides 29 tools through the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/), giving any MCP-compatible AI full read/write access to your palace.

## Setup

### Setup Helper

Cognitive Castle includes a setup helper that prints the exact configuration commands for your environment:

```bash
castle mcp
```

### Manual Connection

```bash
claude mcp add castle -- python -m cognitive_castle.mcp_server
```

### With Custom Palace Path

```bash
claude mcp add castle -- python -m cognitive_castle.mcp_server --palace /path/to/palace
```

Now your AI has all 29 tools available. Ask it anything:

> *"What did we decide about auth last month?"*

Claude calls `castle_search` automatically, gets verbatim results, and answers you.

## Compatible Tools

Cognitive Castle works with any tool that supports MCP:

- **Claude Code** — native via plugin or manual MCP
- **OpenClaw** — via official skill, see [OpenClaw Skill](/guide/openclaw)
- **ChatGPT** — via MCP bridge
- **Cursor** — native MCP support
- **Gemini CLI** — see [Gemini CLI guide](/guide/gemini-cli)

## Memory Protocol

When the AI first calls `castle_status`, it receives the **Memory Protocol** — a behavior guide that teaches it to:

1. **On wake-up**: Call `castle_status` to load the palace overview
2. **Before responding** about any person, project, or past event: search first, never guess
3. **If unsure**: Say "let me check" and query the palace
4. **After each session**: Write diary entries to record what happened
5. **When facts change**: Invalidate old facts, add new ones

This protocol is what turns storage into memory — the AI knows to verify before speaking.

## Tool Overview

### Palace (read)

| Tool | What |
|------|------|
| `castle_status` | Palace overview + AAAK spec + memory protocol |
| `castle_list_wings` | Wings with counts |
| `castle_list_rooms` | Rooms within a wing |
| `castle_get_taxonomy` | Full wing → room → count tree |
| `castle_search` | Semantic search with wing/room filters |
| `castle_check_duplicate` | Check before filing |
| `castle_get_aaak_spec` | AAAK dialect reference |

### Drawers (read)

| Tool | What |
|------|------|
| `castle_get_drawer` | Fetch a single drawer by ID |
| `castle_list_drawers` | List drawers with pagination |

### Palace (write)

| Tool | What |
|------|------|
| `castle_add_drawer` | File verbatim content |
| `castle_update_drawer` | Update drawer content or metadata |
| `castle_delete_drawer` | Remove by ID |

### Knowledge Graph

| Tool | What |
|------|------|
| `castle_kg_query` | Entity relationships with time filtering |
| `castle_kg_add` | Add facts |
| `castle_kg_invalidate` | Mark facts as ended |
| `castle_kg_timeline` | Chronological entity story |
| `castle_kg_stats` | Graph overview |

### Navigation

| Tool | What |
|------|------|
| `castle_traverse` | Walk the graph from a room across wings |
| `castle_find_tunnels` | Find rooms bridging two wings |
| `castle_graph_stats` | Graph connectivity overview |

### Tunnels

| Tool | What |
|------|------|
| `castle_create_tunnel` | Create an explicit cross-wing tunnel |
| `castle_list_tunnels` | List all explicit tunnels |
| `castle_delete_tunnel` | Delete an explicit tunnel |
| `castle_follow_tunnels` | Follow tunnels out from a room |

### Agent Diary

| Tool | What |
|------|------|
| `castle_diary_write` | Write AAAK diary entry |
| `castle_diary_read` | Read recent diary entries |

### System

| Tool | What |
|------|------|
| `castle_hook_settings` | Get or set hook behavior |
| `castle_memories_filed_away` | Check whether the last checkpoint was saved |
| `castle_reconnect` | Force reconnect to the database |

For detailed schemas and parameters, see [MCP Tools Reference](/reference/mcp-tools).
