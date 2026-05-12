# Demo GIFs (PR #2 of productization series) — Design

**Date:** 2026-05-12
**Branch target:** develop
**Scope:** Add 4 recorded demo GIFs to the README — hero (full pitch arc), Quickstart, Verbatim recall, MCP-in-Claude-Code. New `assets/demos/` directory with VHS `.tape` scripts and asciinema `.cast` source for reproducibility. README integrated with inline `![](...)` image references at 4 locations. No production code touched.

## Background

PR #11 productized the README (hero SVG, two Mermaid diagrams, comparison section). The README now communicates the *concept* but doesn't show the *experience* — what the system actually feels like to use. The user explicitly requested a screencast as PR #2 of the productization series.

The decisions locked during the brainstorming session that produced this spec:
1. **Tool:** VHS (Charm.sh) for deterministic recordings of `castle` CLI commands. Asciinema (with `agg` converter) for demo #4 because Claude Code is interactive and can't be scripted in VHS.
2. **Scope:** All 4 demos in this PR. Mixed tooling (VHS × 3 + asciinema × 1).
3. **Asset layout:** `assets/demos/` with paired source (`.tape` / `.cast`) and rendered (`.gif`) files. Plus a regen-instructions README in that folder.
4. **Styling:** Catppuccin Mocha theme, JetBrains Mono font, 1200×640 hero / 900×420 inline.
5. **Storyboards:** Locked for all 4 demos (full scripts in this spec).
6. **Placement:** Hero at top of README (below existing SVG hero + title + badges), inline demos at their relevant sections.

This is PR #2 of a 6-piece productization series:
1. ✅ README + diagrams (PR #11, merged)
2. ← **this PR**
3. Landing page
4. Comparison microsite
5. Launch post drafts
6. Sample palace download

## Goals

1. First-paint impression: hero GIF shows the full Castle loop (install → init → mine → status → search → wake-up) within the first viewport of the README.
2. Each major README section (Quickstart, How it works, Connect to Claude Code) has a 15-30s demo grounding its text.
3. All 3 VHS demos are reproducible: anyone with `vhs` installed can regenerate the GIFs from the committed `.tape` files.
4. Asset weight ≤ 4 MB total (target ~3.2 MB).
5. README line delta ≤ 20 lines added.
6. No production code modified.

## Non-goals

- Landing page or microsite (deferred to PR #3)
- Recording for non-Claude-Code MCP clients (deferred — Castle's audience is primarily Claude Code users)
- Animated SVG demos (decided: all 4 are GIFs for format uniformity, even though asciinema can produce SVG)
- A "demo gallery" page or `docs/DEMOS.md` (the README is the single source of truth for now; if/when more demos exist, revisit)
- Custom VHS theme matching the badge palette exactly (Catppuccin Mocha is close enough; brand-pixel-perfect deferred)
- ttyd / vhs / asciinema being pre-installed on the implementer's machine (the plan documents install steps; this spec assumes the user has admin rights to install via brew/go/cargo/pip)

## Source of truth

- Locked brainstorming decisions: see "Background" section above.
- Current README state: `README.md` post-PR-#11 merge (commit `df883fea`), 348 lines.
- Existing `assets/` directory: confirmed empty as of this spec.
- VHS version recommendation: ≥ 0.7 (supports custom themes and `Require` directive). User installs latest via `brew install vhs` or `go install github.com/charmbracelet/vhs@latest`.

## File-by-file change list

### Added — `assets/demos/`

- `assets/demos/01-hero.tape` (VHS script, ~50 lines)
- `assets/demos/01-hero.gif` (recorded output, ~1.4 MB)
- `assets/demos/02-quickstart.tape` (~20 lines)
- `assets/demos/02-quickstart.gif` (~450 KB)
- `assets/demos/03-verbatim.tape` (~25 lines)
- `assets/demos/03-verbatim.gif` (~750 KB)
- `assets/demos/04-mcp.cast` (asciinema recording, JSON text format, ~30 KB)
- `assets/demos/04-mcp.gif` (`agg`-rendered GIF, ~600 KB)
- `assets/demos/recording-script.md` (~40 lines — exactly what the human types during demo #4 recording, since asciinema captures a live session)
- `assets/demos/README.md` (~80 lines — install commands, regen commands, demo-palace setup)

### Added — `scripts/`

- `scripts/record-demos.sh` (~60 lines — automates demo-palace setup and VHS runs for demos 1-3; instructs user to manually record demo #4 with asciinema)

### Modified — `README.md`

4 single-line additions (plus alt text):
- After badges in the `<div align="center">` block: `![alt](assets/demos/01-hero.gif)`
- After the Quickstart code block: `![alt](assets/demos/02-quickstart.gif)`
- After the Mermaid data flow in "How it works": `![alt](assets/demos/03-verbatim.gif)`
- After the plugin install block in "Connect to Claude Code": `![alt](assets/demos/04-mcp.gif)`

Total README delta: +12-16 lines (4 markdown image lines + some surrounding prose like "Here's what that looks like:" or "30 seconds of the full loop:").

### Untouched

- All production code (`cognitive_castle/`, `tests/`, `pyproject.toml`, `.claude-plugin/`)
- Existing README structure and content from PR #11 (the demos are *additions*, not replacements)
- Existing `assets/` (besides the new `demos/` subfolder)

## The 4 demo storyboards

### Demo #1 — Hero (full pitch arc, ~40s)

`assets/demos/01-hero.tape`:

```
Output assets/demos/01-hero.gif

Require castle

Set FontFamily "JetBrains Mono"
Set FontSize 14
Set Width 1200
Set Height 640
Set Theme "Catppuccin Mocha"
Set TypingSpeed 50ms
Set Padding 20
Set Margin 0
Set Shell "bash"

# Open with title comment
Type "# Cognitive Castle — local-first AI memory"
Sleep 1.5s
Enter
Sleep 1s

# Install
Type "pip install cognitive-castle"
Enter
Sleep 2s

# Init a small demo palace (path matches scripts/record-demos.sh)
Type "castle init /tmp/castle-demo-src --palace /tmp/castle-demo-palace --yes"
Enter
Sleep 6s

# Mine some conversation transcripts
Type "castle mine ~/.claude/projects --mode convos"
Enter
Sleep 4s

# Show scale via status
Type "castle status"
Enter
Sleep 3s

# Real search hit
Type 'castle search "3-stage retrieval pipeline"'
Enter
Sleep 4s

# Wake-up context
Type "castle wake-up --wing castle"
Enter
Sleep 3s

# Closing punch
Type "# No API key. Nothing left your laptop."
Sleep 3s
```

### Demo #2 — Quickstart loop (~13s)

`assets/demos/02-quickstart.tape`:

```
Output assets/demos/02-quickstart.gif

Require castle

Set FontFamily "JetBrains Mono"
Set FontSize 12
Set Width 900
Set Height 420
Set Theme "Catppuccin Mocha"
Set TypingSpeed 50ms
Set Padding 20

Type "pip install cognitive-castle"
Enter
Sleep 2s

Type "castle init /tmp/castle-demo-src --palace /tmp/castle-demo-palace --yes"
Enter
Sleep 5s

Type 'castle --palace /tmp/castle-demo-palace search "why did we switch to graphql"'
Enter
Sleep 3s

Type 'castle --palace /tmp/castle-demo-palace search "auth flow" --wing castle-demo-src --room general'
Enter
Sleep 3s
```

### Demo #3 — Verbatim recall (~20s)

`assets/demos/03-verbatim.tape`:

```
Output assets/demos/03-verbatim.gif

Require castle

Set FontFamily "JetBrains Mono"
Set FontSize 12
Set Width 900
Set Height 420
Set Theme "Catppuccin Mocha"
Set TypingSpeed 50ms
Set Padding 20

Type "# Mine the Cognitive Castle repo into a palace"
Enter
Sleep 1s

Type "castle mine ~/cognitive-castle --wing castle"
Enter
Sleep 6s

Type "# Search for a real architecture decision"
Enter
Sleep 1s

Type 'castle search "why did we remove ChromaDB"'
Enter
Sleep 5s

# Output: verbatim text from PR #8 description appears

Type "# That's the exact text. No summarization."
Sleep 3s
```

### Demo #4 — MCP in Claude Code (~30s)

`assets/demos/recording-script.md` documents the exact sequence for the human recorder:

```
1. In a terminal: cd ~/cognitive-castle && asciinema rec assets/demos/04-mcp.cast

2. Within the recording, launch Claude Code: `claude`

3. Confirm Castle plugin is loaded by typing in the prompt:
   /castle:status

   Wait for response showing palace stats.

4. Press Esc to clear, then type the demo prompt:
   What did we decide about the embedder model? Search Castle for the
   specific decision and tell me why we picked it.

5. Claude will call castle_search MCP tool. The verbatim result
   appears in the Castle MCP tool-use block. Claude then responds
   citing the retrieved content.

6. Wait for the response to finish. Total elapsed ~25-30 seconds.

7. Press Ctrl+C twice to exit Claude Code, then Ctrl+D to end
   asciinema recording.

8. Convert the cast to a GIF:
   agg --theme=monokai --speed=1.5 --font-size=14 \
       assets/demos/04-mcp.cast assets/demos/04-mcp.gif

   (Adjust --speed and --font-size based on what looks right.)
```

This is the only demo that's not deterministic. The recording captures a real Claude Code session; Claude's response timing and exact wording will vary. That's acceptable for a demo — the *what* matters more than the *when*.

## VHS / asciinema setup

### Install commands

The plan's setup step has these:

```bash
# VHS — terminal recorder
go install github.com/charmbracelet/vhs@latest
# OR: brew install vhs
# OR: download a binary release from charm.sh/vhs

# ttyd — VHS dependency
brew install ttyd
# OR: see https://github.com/tsl0922/ttyd/releases

# JetBrains Mono — used by VHS theme
# macOS: brew install --cask font-jetbrains-mono
# Linux: install via package manager or unzip from JetBrains release

# asciinema — for demo #4
brew install asciinema
# OR: pip install asciinema

# agg — asciinema-to-gif converter
brew install agg
# OR: cargo install --git https://github.com/asciinema/agg
```

### Demo palace setup (one-time, before recording)

To ensure deterministic timings, demos 1-3 record commands against a fresh demo palace. `scripts/record-demos.sh` handles setup:

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1. Create a small demo source directory
mkdir -p /tmp/castle-demo-src
echo "# myapp" > /tmp/castle-demo-src/README.md
echo "# Auth flow uses JWT bearer tokens..." > /tmp/castle-demo-src/auth.md
echo "# GraphQL replaced REST in Q3..." > /tmp/castle-demo-src/decisions.md

# 2. Pre-warm the embedder
castle init /tmp/castle-demo-src --palace /tmp/castle-demo-palace --yes 2>&1 | tail -3

# 3. Record demos 1-3
cd assets/demos
vhs 01-hero.tape
vhs 02-quickstart.tape
vhs 03-verbatim.tape

echo
echo "Demos 1-3 done. For demo #4, follow assets/demos/recording-script.md"
echo "to manually record the Claude Code MCP session via asciinema."
```

## README integration

4 single-line additions, each with descriptive alt text:

```markdown
<!-- after the badges, inside the existing <div align="center"> -->

![Cognitive Castle 40-second demo — install, init, mine, status, search, wake-up](assets/demos/01-hero.gif)
```

```markdown
<!-- after the Quickstart 4-step code block -->

![Quickstart demo — install, init, search](assets/demos/02-quickstart.gif)
```

```markdown
<!-- in "How it works", after the Mermaid data flow -->

**See verbatim retrieval in action:**

![Verbatim recall demo — search returns the exact text from a real architecture decision](assets/demos/03-verbatim.gif)
```

```markdown
<!-- in "Connect to Claude Code", after the plugin install code block -->

**What it looks like in a Claude Code session:**

![MCP demo — Claude using Castle's castle_search tool mid-conversation](assets/demos/04-mcp.gif)
```

## Testing strategy

1. **`.tape` reproducibility:** running `vhs assets/demos/0X-name.tape` on a fresh checkout reproduces the GIF deterministically (modulo embedder loading time on first invocation — pre-warmed via `scripts/record-demos.sh`).

2. **Asset size sanity:**
   ```
   du -sh assets/demos/*.gif
   ```
   Each GIF should be ≤ 1.5 MB; total ≤ 4 MB.

3. **README render:** view rendered README on github.com after pushing the branch. Confirm all 4 inline GIFs load and play.

4. **Alt text:** all 4 `![]()` lines have descriptive alt text (≥ 30 characters each).

5. **Line delta:** `git diff develop..HEAD -- README.md | grep -c '^+'` shows ≤ 20 net added lines for README changes.

## Risk

- **Low for the code changes, moderate for the recording workflow.** The implementer-produced files (`.tape`, `.md`, `.sh`) are all text and reviewable; the rendered GIFs depend on the user's local environment matching what's in `.tape` files.
- **VHS install can fail** on minimal Linux systems (needs ttyd, Chrome/Chromium headless internally). If install fails, fall back to demo #2-3 only via terminalizer (deferred) or skip the GIFs and ship only #1+#4. Document this fallback in `assets/demos/README.md`.
- **JetBrains Mono not installed** → VHS falls back to a generic monospace, which looks fine but loses the polish. Not a blocker.
- **Demo #4 (MCP) requires real Castle state on the user's machine.** The user is already using Castle daily (per the live install confirmation earlier in this session), so this is fine — the demo recording uses the user's actual palace state.
- **First-paint weight:** ~3.2 MB of GIFs in the README adds load time. The 4 demos cluster around different sections, so the browser loads them incrementally as the user scrolls. Acceptable trade for the impact.

## Acceptance criteria

1. `assets/demos/` directory exists with all 10 expected files (4 `.tape` + `.cast`, 4 `.gif`, 1 `recording-script.md`, 1 `README.md`).
2. Each `.tape` file is committed and matches the storyboards in this spec exactly (or with minor timing adjustments documented in the file).
3. `scripts/record-demos.sh` exists, is executable (`chmod +x`), and runs without error on a Linux box with VHS installed and the embedder pre-warmed.
4. `assets/demos/README.md` documents the regen commands for all 4 demos (VHS + asciinema + agg) and the demo-palace setup.
5. `README.md` has 4 inline `![](assets/demos/0X-*.gif)` references at the placements described above.
6. Each `![](...)` has descriptive alt text ≥ 30 characters.
7. `du -sh assets/demos/` shows ≤ 4 MB total.
8. `git diff develop..HEAD -- README.md | grep -c '^+'` shows ≤ 20 added lines for README changes.
9. No production code under `cognitive_castle/`, `tests/`, `pyproject.toml`, `.claude-plugin/` is modified.
10. All 4 GIFs render correctly when viewed at `github.com/Testimonial/cognitive-castle/blob/<branch>/README.md` (visual check by user).
11. Demos 1-3 are reproducible: deleting any GIF and re-running `vhs <tape-file>` produces an equivalent output (timing tolerance ±20%).
12. PR body explains the 4 demos and links to the brainstorm spec.
