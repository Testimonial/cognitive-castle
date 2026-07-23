# CLI Commands

All commands accept `--palace <path>` to override the default palace location.

## `castle init`

Scan a project directory for people, projects, and rooms, and set up the palace.

```bash
castle init <dir>                 # <dir> is required
castle init <dir> --yes           # non-interactive mode
castle init ~/projects/myapp      # example
castle init .                     # initialize from the current directory
```

| Option  | Description                                                                  |
|---------|------------------------------------------------------------------------------|
| `<dir>` | **Required.** Project directory to scan. Pass `.` for the current directory. |
| `--yes` | Auto-accept all detected entities                                            |

What it does:

1. Scans `<dir>` for people and projects in file content
2. Detects rooms from `<dir>`'s folder structure
3. Saves detected entities to `<dir>/entities.json`
4. Ensures the global `~/.castle/` config directory exists

Running `castle init` with no argument will exit with
`error: the following arguments are required: dir`.

## `castle mine`

Mine files into the palace.

```bash
castle mine <dir>
castle mine <dir> --mode convos
castle mine <dir> --mode convos --extract general
castle mine <dir> --wing myapp
```

| Option | Default | Description |
|--------|---------|-------------|
| `<dir>` | — | Directory to mine |
| `--mode` | `projects` | `projects` for code/docs, `convos` for chat exports |
| `--wing` | directory name | Wing name override |
| `--agent` | `castle` | Agent name tag |
| `--limit` | `0` (all) | Max files to process |
| `--dry-run` | — | Preview without filing |
| `--extract` | `exchange` | `exchange` or `general` (for convos mode) |
| `--no-gitignore` | — | Don't respect .gitignore |
| `--include-ignored` | — | Always scan these paths even if ignored |

## `castle search`

Find anything by semantic search.

```bash
castle search "query"
castle search "query" --wing myapp
castle search "query" --wing myapp --room auth
castle search "query" --results 10
```

| Option | Default | Description |
|--------|---------|-------------|
| `"query"` | — | What to search for |
| `--wing` | all | Filter by wing |
| `--room` | all | Filter by room |
| `--results` | `5` | Number of results |

## `castle split`

Split concatenated transcript mega-files into per-session files.

```bash
castle split <dir>
castle split <dir> --dry-run
castle split <dir> --min-sessions 3
castle split <dir> --output-dir ~/split-output/
```

| Option | Default | Description |
|--------|---------|-------------|
| `<dir>` | — | Directory with transcript files |
| `--output-dir` | same dir | Write split files here |
| `--dry-run` | — | Preview without writing |
| `--min-sessions` | `2` | Only split files with N+ sessions |

## `castle wake-up`

Show L0 + L1 wake-up context (~600–900 tokens).

```bash
castle wake-up
castle wake-up --wing driftwood
```

| Option | Description |
|--------|-------------|
| `--wing` | Project-specific wake-up |

## `castle compress`

Compress drawers using AAAK Dialect.

```bash
castle compress --wing myapp
castle compress --wing myapp --dry-run
castle compress --config entities.json
```

| Option | Description |
|--------|-------------|
| `--wing` | Wing to compress (default: all) |
| `--dry-run` | Preview without storing |
| `--config` | Entity config JSON file |

## `castle status`

Show what's been filed — drawer count, wing/room breakdown.

```bash
castle status
```

## `castle repair`

Rebuild palace vector index from stored data. Fixes segfaults after database corruption.

```bash
castle repair
```

Creates a backup at `<palace_path>.backup` before rebuilding.

## `castle mcp`

Helper command that outputs setup syntax (like `claude mcp add...`) to connect Cognitive Castle to your AI client, automatically handling paths.

```bash
castle mcp
castle mcp --palace ~/.custom-palace
```

## `castle hook`

Run hook logic for Claude Code / Codex integration.

```bash
castle hook run --hook stop --harness claude-code
castle hook run --hook precompact --harness claude-code
castle hook run --hook session-start --harness codex
```

| Option | Values | Description |
|--------|--------|-------------|
| `--hook` | `session-start`, `stop`, `precompact` | Hook name |
| `--harness` | `claude-code`, `codex` | Harness type |

## `castle instructions`

Output skill instructions to stdout.

```bash
castle instructions init
castle instructions search
castle instructions mine
castle instructions help
castle instructions status
```
