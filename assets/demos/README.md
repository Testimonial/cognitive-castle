# Demos

Recordings used in the main `README.md`. Regenerate them with `scripts/record-demos.sh`.

## What's here

| File | What it shows | Format |
|---|---|---|
| `01-hero.tape` / `01-hero.gif` | Full pitch arc (~40s) — install, init, mine, status, search, wake-up | VHS |
| `02-quickstart.tape` / `02-quickstart.gif` | Quickstart loop (~13s) — install, init, scoped search | VHS |
| `03-verbatim.tape` / `03-verbatim.gif` | Verbatim recall (~20s) — mine the Castle repo, search a real PR decision | VHS |
| `04-mcp.expect` | **WIP scaffolding** for a future MCP-in-Claude-Code demo (asciinema + agg). Currently can't record cleanly when another `claude` session is active on the same machine — Castle MCP fails to initialize in the spawned context. Deferred to a follow-up PR. |

## Regenerating

One command from the repo root:

```bash
./scripts/record-demos.sh
```

### What it does

1. Cleans `/tmp/castle-demo-src` and `/tmp/castle-demo-palace`.
2. Writes a tiny demo project to `/tmp/castle-demo-src`.
3. Pre-warms the embedder.
4. Runs `vhs` against demos 1-3 — outputs land at `assets/demos/0X-name.gif`.
5. Attempts to run `assets/demos/04-mcp.expect` — currently fails when another `claude` session is active. See "WIP" caveat above. The recording for demo #4 is deferred to a follow-up PR.

The committed `.gif` files were further compressed via `ffmpeg` (10fps, 32-color palette, optional downscale) to keep the asset weight under 4 MB. Regenerate the post-VHS compressed versions with the one-liner shown under "Regenerating just one demo" below.

### One-time prereqs

```bash
# VHS — terminal recorder
go install github.com/charmbracelet/vhs@latest
# or: brew install vhs

# ttyd — VHS dependency
brew install ttyd

# JetBrains Mono — VHS theme uses it (falls back if missing)
brew install --cask font-jetbrains-mono

# asciinema — for demo #4
brew install asciinema   # or pip install asciinema

# agg — asciinema-to-gif converter
brew install agg   # or cargo install --git https://github.com/asciinema/agg

# expect — drives claude programmatically
brew install expect   # pre-installed on macOS; apt install expect on Debian
```

### Demo #4 caveats

- Burns Anthropic API tokens on each regen (a few cents per recording).
- Won't run in CI without an `ANTHROPIC_API_KEY` secret AND a token budget.
- Claude's response wording varies per regen — that's expected. The demo shows the *experience* (tool call + verbatim hit + response), not a fixed transcript.
- The `expect` regex patterns in `04-mcp.expect` may need tweaking if Claude Code updates its TUI.

## Regenerating just one demo

```bash
# Demo 1, 2, or 3:
vhs assets/demos/01-hero.tape

# Demo 4:
./assets/demos/04-mcp.expect
```
