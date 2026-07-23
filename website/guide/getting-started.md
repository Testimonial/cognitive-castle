# Getting Started

## Installation

Cognitive Castle is installed from source (not published to PyPI):

```bash
git clone https://github.com/Testimonial/cognitive-castle.git
cd cognitive-castle
pip install -e ".[dev]"
```

After install, the `castle` and `castle-mcp` commands are on `$PATH`.

::: danger Watch out for brand-squatting
Cognitive Castle's official code lives only at
[github.com/Testimonial/cognitive-castle](https://github.com/Testimonial/cognitive-castle).
Historical drift from Castle's upstream ancestor MemPalace has attracted
brand-squatting look-alike domains (e.g. `mempalace.tech`) that have hosted
ad-redirects and potential malware. Never install binaries, scripts, or
pip packages from unofficial domains, PyPI mirrors, or any URL you did
not verify against the official repo above.
:::

### Requirements

- Python 3.9+
- `lancedb>=0.20` (installed automatically)
- `pyyaml>=6.0` (installed automatically)

No API key required for the core local workflow. After installation, the main storage and retrieval path runs locally.

## Quick Start

Three steps: **init**, **mine**, **search**.

### 1. Initialize Your Palace

`castle init` requires a project directory to scan. Pass a path,
or `.` to use the current directory.

```bash
castle init ~/projects/myapp
# or, from inside the project:
castle init .
```

This scans your project directory and:

- Detects people and projects from file content
- Creates rooms from your folder structure
- Ensures the `~/.castle/` config directory exists

### 2. Mine Your Data

```bash
# Mine project files (code, docs, notes)
castle mine ~/projects/myapp

# Mine conversation exports (Claude, ChatGPT, Slack)
castle mine ~/chats/ --mode convos

# Mine with auto-classification into memory types
castle mine ~/chats/ --mode convos --extract general
```

Two mining modes plus one extraction strategy:
- **projects** — code and docs, auto-detected rooms
- **convos** — conversation exports, chunked by exchange pair
- **general extraction** — an `--extract general` option for conversation mining that classifies content into decisions, preferences, milestones, problems, and emotional context

### 3. Search

```bash
castle search "why did we switch to GraphQL"
```

That gives you a working local memory index.

## What Happens Next

After the one-time setup, you don't run Cognitive Castle commands manually. Your AI uses it for you through [MCP integration](/guide/mcp-integration) or a [Claude Code plugin](/guide/claude-code).

Ask your AI anything:

> *"What did we decide about auth last month?"*

It calls `castle_search` automatically, gets verbatim results, and answers you. You never type `castle search` again.

## Next Steps

- [Mining Your Data](/guide/mining) — deep dive into mining modes
- [MCP Integration](/guide/mcp-integration) — connect to Claude, ChatGPT, Cursor, Gemini
- [The Palace](/concepts/the-palace) — understand wings, rooms, halls, and tunnels
