# Cognitive Castle Claude Code Plugin

A Claude Code plugin that gives your AI a persistent memory system. Mine projects and conversations into a searchable palace backed by LanceDB, with MCP tools, auto-save hooks, and 5 guided skills.

## Prerequisites

- Python 3.9+
- `git clone https://github.com/Testimonial/cognitive-castle.git && cd cognitive-castle && pip install -e .` (Cognitive Castle is not yet on PyPI)

## Installation

### From this repository

Inside Claude Code:

```
/plugin marketplace add /path/to/cognitive-castle
/plugin install castle@cognitive-castle
```

Then fully quit and reopen Claude Code (a `/reload` is not enough for new MCP servers).

## Post-Install Setup

After installing the plugin, run the init command to complete setup (pip install, MCP configuration, palace creation, etc.):

```
/castle:init
```

## Available Slash Commands

| Command | Description |
|---------|-------------|
| `/castle:help` | Show available tools, skills, and architecture |
| `/castle:init` | Set up Cognitive Castle — install, configure MCP, onboard |
| `/castle:search` | Search your memories across the palace |
| `/castle:mine` | Mine projects and conversations into the palace |
| `/castle:status` | Show palace overview — wings, rooms, drawer counts |

## Hooks

Cognitive Castle registers two hooks that run automatically:

- **Stop** — Saves conversation context every 15 messages.
- **PreCompact** — Preserves important memories before context compaction.

Set the `CASTLE_DIR` environment variable to a directory path to automatically run `castle mine` on that directory during each save trigger. (Legacy `MEMPAL_DIR` is still read with a one-time deprecation warning per process.)

## MCP Server

The plugin automatically configures a local MCP server with 30 tools for storing, searching, and managing memories. No manual MCP setup is required — `/castle:init` handles everything.

## Full Documentation

See the main [README](../README.md) for complete documentation, architecture details, and advanced usage.
