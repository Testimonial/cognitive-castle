# Cognitive Castle

AI memory system. Store everything, find anything. Local, free, no API key.

---

## Slash Commands

| Command              | Description                    |
|----------------------|--------------------------------|
| /castle:init      | Install and set up Cognitive Castle   |
| /castle:search    | Search your memories           |
| /castle:mine      | Mine projects and conversations|
| /castle:status    | Palace overview and stats      |
| /castle:help      | This help message              |

---

## MCP Tools (19)

### Palace (read)
- castle_status -- Palace status and stats
- castle_list_wings -- List all wings
- castle_list_rooms -- List rooms in a wing
- castle_get_taxonomy -- Get the full taxonomy tree
- castle_search -- Search memories by query
- castle_check_duplicate -- Check if a memory already exists
- castle_get_aaak_spec -- Get the AAAK specification

### Palace (write)
- castle_add_drawer -- Add a new memory (drawer)
- castle_delete_drawer -- Delete a memory (drawer)

### Knowledge Graph
- castle_kg_query -- Query the knowledge graph
- castle_kg_add -- Add a knowledge graph entry
- castle_kg_invalidate -- Invalidate a knowledge graph entry
- castle_kg_timeline -- View knowledge graph timeline
- castle_kg_stats -- Knowledge graph statistics

### Navigation
- castle_traverse -- Traverse the palace structure
- castle_find_tunnels -- Find cross-wing connections
- castle_graph_stats -- Graph connectivity statistics

### Agent Diary
- castle_diary_write -- Write a diary entry
- castle_diary_read -- Read diary entries

---

## CLI Commands

    castle init <dir>                  Initialize a new palace
    castle mine <dir>                  Mine a project (default mode)
    castle mine <dir> --mode convos    Mine conversation exports
    castle search "query"              Search your memories
    castle split <dir>                 Split large transcript files
    castle wake-up                     Load palace into context
    castle compress                    Compress palace storage
    castle status                      Show palace status
    castle repair                      Rebuild vector index
    castle mcp                         Show MCP setup command
    castle hook run                    Run hook logic (for harness integration)
    castle instructions <name>         Output skill instructions

---

## Auto-Save Hooks

- Stop hook -- Automatically saves memories every 15 messages. Counts human
  messages in the session transcript (skipping command-messages). When the
  threshold is reached, blocks the AI with a save instruction. Uses
  ~/.castle/hook_state/ to track save points per session. If
  stop_hook_active is true, passes through to prevent infinite loops.

- PreCompact hook -- Emergency save before context compaction. Always blocks
  with a comprehensive save instruction because compaction means the AI is
  about to lose detailed context.

Hooks read JSON from stdin and output JSON to stdout. They can be invoked via:

    echo '{"session_id":"abc","stop_hook_active":false,"transcript_path":"..."}' | castle hook run --hook stop --harness claude-code

---

## Architecture

    Wings (projects/people)
      +-- Rooms (topics)
            +-- Closets (summaries)
                  +-- Drawers (verbatim memories)

    Halls connect rooms within a wing.
    Tunnels connect rooms across wings.

The palace is stored locally using LanceDB for vector and full-text search,
and SQLite for the knowledge graph. No cloud services or API keys required.

---

## Getting Started

1. /castle:init -- Set up your palace
2. /castle:mine -- Mine a project or conversation
3. /castle:search -- Find what you stored
