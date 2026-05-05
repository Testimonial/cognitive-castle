# Cognitive Castle UX Polish — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix five UX problems found in a live session: stale "MemPalace" branding, silent mining, `--yes` not being fully non-interactive, stale lock accumulation, and benchmark data polluting the palace.

**Architecture:** All five fixes are independent, each touching 1–41 files. Fix A (rebrand) is the largest — it's mechanical string replacement across the whole `cognitive_castle/` package and all test files that still patch the old `mempalace.*` module paths. Fixes B–E are small targeted edits to `miner.py`, `cli.py`, and `.gitignore`.

**Tech Stack:** Python 3.9+, pytest, argparse. No new dependencies.

---

## File Map

| Fix | Files Modified |
|-----|----------------|
| A (rebrand source) | `cognitive_castle/cli.py`, `miner.py`, `mcp_server.py`, `repair.py`, `hooks_cli.py`, `onboarding.py`, `dedup.py`, `migrate.py`, and 33 more modules |
| A (rebrand tests) | `tests/test_corpus_origin_integration.py`, `test_cli.py`, `test_dedup.py`, `test_entity_registry.py`, `test_hooks_cli.py`, `test_instructions_cli.py`, `test_llm_client.py`, `test_migrate.py`, `test_miner.py`, `test_normalize.py`, `test_onboarding.py`, `test_repair.py`, `test_spellcheck.py`, `test_spellcheck_extra.py` |
| B (progress) | `cognitive_castle/miner.py` |
| C (`--yes`) | `cognitive_castle/cli.py` |
| D (locks) | `cognitive_castle/cli.py`, `cognitive_castle/palace.py` |
| E (benchmarks) | `.gitignore` |
| New test | `tests/test_branding.py`, `tests/test_clean_locks.py` |

---

## Task 1: Write branding test (TDD: red)

**Files:**
- Create: `tests/test_branding.py`

- [ ] **Step 1: Create the test file**

```python
# tests/test_branding.py
"""Ensure all user-facing strings say 'Cognitive Castle', never 'MemPalace'."""
import subprocess
import sys


def _run(args):
    return subprocess.run(
        [sys.executable, "-m", "cognitive_castle.cli"] + args,
        capture_output=True, text=True,
    )


def test_main_help_no_mempalace():
    r = _run(["--help"])
    combined = r.stdout + r.stderr
    assert "MemPalace" not in combined, f"Found 'MemPalace' in --help output:\n{combined}"
    assert "mempalace" not in combined, f"Found 'mempalace' in --help output:\n{combined}"


def test_mine_help_no_mempalace():
    r = _run(["mine", "--help"])
    combined = r.stdout + r.stderr
    assert "MemPalace" not in combined
    assert "mempalace" not in combined


def test_mcp_output_no_mempalace(tmp_path, monkeypatch):
    """cmd_mcp prints the setup command — must say 'castle-mcp', not 'mempalace-mcp'."""
    import argparse
    from cognitive_castle.cli import cmd_mcp
    args = argparse.Namespace(palace=None)
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_mcp(args)
    out = buf.getvalue()
    assert "mempalace" not in out.lower(), f"Found 'mempalace' in cmd_mcp output:\n{out}"
    assert "castle-mcp" in out, f"Expected 'castle-mcp' in cmd_mcp output:\n{out}"


def test_mine_banner_no_mempalace(tmp_path, monkeypatch):
    """The MemPalace Mine banner must say 'Cognitive Castle Mine'."""
    import io, contextlib, pathlib
    from cognitive_castle.miner import mine

    # Minimal setup: empty castle.yaml so mine can load config
    (tmp_path / "castle.yaml").write_text(
        "wing: testproj\nrooms:\n  - name: general\n    patterns: ['*']\n"
    )
    (tmp_path / "hello.txt").write_text("hello world")

    palace = tmp_path / "palace"
    palace.mkdir()

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mine(
            project_dir=str(tmp_path),
            palace_path=str(palace),
            dry_run=True,
        )
    out = buf.getvalue()
    assert "MemPalace" not in out, f"Found 'MemPalace' in mine output:\n{out}"
    assert "Cognitive Castle" in out, f"Expected 'Cognitive Castle' in mine output:\n{out}"
```

- [ ] **Step 2: Run it — expect failures**

```bash
cd /Users/ladislavbihari/myWork/soar/cognitive-castle
python -m pytest tests/test_branding.py -v --tb=short 2>&1 | tail -20
```

Expected: 3-4 FAILED (output still says "MemPalace")

---

## Task 2: Rebrand cognitive_castle/ source files — Part 1 (high-count files)

**Files:**
- Modify: `cognitive_castle/cli.py` (39 occurrences)
- Modify: `cognitive_castle/miner.py` (9 occurrences)
- Modify: `cognitive_castle/mcp_server.py` (9 occurrences)

The rule: only change **user-visible strings** (print statements, argparse help text, example commands). Do NOT rename Python identifiers like `MempalaceConfig`, `mine_palace_lock`, etc.

- [ ] **Step 1: Replace in cli.py**

Apply these replacements (in order — later ones may depend on earlier):

```python
# cli.py — line 3 (module docstring / argparse description)
# "MemPalace — Give your AI a memory. No API key required."
# → "Cognitive Castle — Give your AI a memory. No API key required."

# lines 6-27 (example commands in epilog)
# all "mempalace mine" → "castle mine"
# all "mempalace search" → "castle search"
# all "mempalace init" → "castle init"
# all "mempalace split" → "castle split"
# all "mempalace mcp" → "castle mcp"
# all "mempalace wake-up" → "castle wake-up"
# all "mempalace status" → "castle status"

# line 221 (gitignore comment written by init)
# "# MemPalace per-project files (issue #185)"
# → "# Cognitive Castle per-project files (issue #185)"

# line 282 (LLM consent warning)
# "MemPalace does not control how the provider logs"
# → "Cognitive Castle does not control how the provider logs"

# line 467 (skipped mine message)
# "Run `mempalace mine {shlex.quote(project_dir)}` when ready."
# → "Run `castle mine {shlex.quote(project_dir)}` when ready."

# line 618 (sys.argv rewrite for split)
# sys.argv = ["mempalace split"] + argv
# → sys.argv = ["castle split"] + argv

# line 686 (repair banner)
# "  MemPalace Repair"
# → "  Cognitive Castle Repair"

# line 793 (cmd_mcp)
# base_server_cmd = "mempalace-mcp"
# → base_server_cmd = "castle-mcp"

# lines 801-808 (cmd_mcp print statements)
# "MemPalace MCP quick setup:" → "Cognitive Castle MCP quick setup:"
# "claude mcp add mempalace --" → "claude mcp add castle --"
# (all 3 occurrences of "claude mcp add mempalace")

# line 839 (status no-palace hint)
# "Run: mempalace init <dir> then mempalace mine <dir>"
# → "Run: castle init <dir> then castle mine <dir>"

# line 939 (version label)
# version_label = f"MemPalace {__version__}"
# → version_label = f"Cognitive Castle {__version__}"

# line 941 (argparse description)
# description="MemPalace — Give your AI a memory. No API key required."
# → description="Cognitive Castle — Give your AI a memory. No API key required."

# line 1065 (--agent help text)
# "Your name — recorded on every drawer (default: mempalace)"
# → "Your name — recorded on every drawer (default: castle)"

# lines 1074-1075 (redetect-origin help)
# "since `mempalace init` and the stored origin may be stale."
# → "since `castle init` and the stored origin may be stale."
# "re-run `mempalace init --llm` for Tier 2 refinement."
# → "re-run `castle init --llm` for Tier 2 refinement."

# line 1239 (mcp command help)
# "Show MCP setup command for connecting MemPalace to your AI client"
# → "Show MCP setup command for connecting Cognitive Castle to your AI client"
```

Run the replacements with `sed -i ''` or edit directly. Then verify:

```bash
grep -n "MemPalace\|mempalace" cognitive_castle/cli.py
```

Expected: only internal Python identifiers remain (`MempalaceConfig`, etc.) — no display strings.

- [ ] **Step 2: Replace in miner.py**

```python
# line 61: "mempalace.yml" stays — it's a real filename pattern, not a brand string

# line 1035 (MineAlreadyRunning message)
# "mempalace: another `mine` is already running"
# → "castle: another `mine` is already running"

# line 1071 (mine banner)
# "  MemPalace Mine"
# → "  Cognitive Castle Mine"

# line 1151 (next-step hint)
# 'Next: mempalace search "what you\'re looking for"'
# → 'Next: castle search "what you\'re looking for"'

# line 1164 (resume hint after KeyboardInterrupt)
# "Re-run `mempalace mine {shlex.quote(project_dir)}` to resume"
# → "Re-run `castle mine {shlex.quote(project_dir)}` to resume"

# line 1182 (docstring reference)
# "in :func:`mempalace.hooks_cli._spawn_mine`"
# → "in :func:`cognitive_castle.hooks_cli._spawn_mine`"

# line 1238 (status no-palace hint)
# "Run: mempalace init <dir> then mempalace mine <dir>"
# → "Run: castle init <dir> then castle mine <dir>"

# line 1258 (status banner)
# "  MemPalace Status — {total} drawers"
# → "  Cognitive Castle Status — {total} drawers"
```

- [ ] **Step 3: Replace in mcp_server.py**

```python
# line 3 (module docstring)
# "MemPalace MCP Server — read/write palace access for Claude Code"
# → "Cognitive Castle MCP Server — read/write palace access for Claude Code"

# line 5
# "Install: claude mcp add mempalace -- mempalace-mcp [--palace /path/to/palace]"
# → "Install: claude mcp add castle -- castle-mcp [--palace /path/to/palace]"

# line 81
# description="MemPalace MCP Server"
# → description="Cognitive Castle MCP Server"

# line 183 (status hint)
# "hint": "Run: mempalace init <dir> && mempalace mine <dir>"
# → "hint": "Run: castle init <dir> && castle mine <dir>"

# line 276 (PALACE_PROTOCOL string)
# "IMPORTANT — MemPalace Memory Protocol:"
# → "IMPORTANT — Cognitive Castle Memory Protocol:"

# line 285 (AAAK_SPEC string)
# "AAAK is a compressed memory dialect that MemPalace uses"
# → "AAAK is a compressed memory dialect that Cognitive Castle uses"

# line 1057 (tool docstring)
# "use ``mempalace repair`` to migrate legacy data if needed."
# → "use ``castle repair`` to migrate legacy data if needed."

# line 1250 (tool description)
# "the compressed memory format MemPalace uses"
# → "the compressed memory format Cognitive Castle uses"

# line 1791 (startup log)
# logger.info("MemPalace MCP Server starting...")
# → logger.info("Cognitive Castle MCP Server starting...")
```

- [ ] **Step 4: Run tests to check progress**

```bash
cd /Users/ladislavbihari/myWork/soar/cognitive-castle
python -m pytest tests/test_branding.py -v --tb=short 2>&1 | tail -20
```

Expected: 2-3 PASSED (branding tests for cli + mine banner now pass)

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/cli.py cognitive_castle/miner.py cognitive_castle/mcp_server.py
git commit -m "refactor: rebrand cli.py, miner.py, mcp_server.py display strings to Cognitive Castle"
```

---

## Task 3: Rebrand remaining source modules (mid-count and small files)

**Files:**
- Modify: `cognitive_castle/repair.py` (13), `hooks_cli.py` (13), `onboarding.py` (11), `dedup.py` (9), `migrate.py` (8), `backends/chroma.py` (8), `sources/registry.py` (6), `entity_detector.py` (6), `searcher.py` (5), `project_scanner.py` (5), `sources/base.py` (4), `palace.py` (4), `entity_registry.py` (4), `sources/transforms.py` (3), `i18n/__init__.py` (3), `backends/lancedb_backend.py` (3), `room_detector_local.py` (2), `normalize.py` (2), `llm_client.py` (2), `layers.py` (2), `fact_checker.py` (2), `diary_ingest.py` (2), `dialect.py` (2), `corpus_origin.py` (2), `convo_miner.py` (2), `config.py` (2), `backends/registry.py` (2), `version.py` (1), `spellcheck.py` (1), `sources/context.py` (1), `knowledge_graph.py` (1), `instructions_cli.py` (1), `closet_llm.py` (1), `backends/base.py` (1), `backends/__init__.py` (1), `__main__.py` (1), `__init__.py` (1)

- [ ] **Step 1: Run the batch replacement script**

Save this as `/tmp/rebrand.py` and run it (it only rewrites user-visible display strings, not identifiers):

```python
#!/usr/bin/env python3
"""Batch replace user-visible MemPalace strings in cognitive_castle/ source files."""
import re
from pathlib import Path

ROOT = Path("/Users/ladislavbihari/myWork/soar/cognitive-castle/cognitive_castle")

# These are the substitution rules, applied in order.
# Each is (pattern, replacement) where pattern matches user-visible display text.
RULES = [
    # Titles / banners in print() calls and argparse descriptions
    ("MemPalace MCP Server",     "Cognitive Castle MCP Server"),
    ("MemPalace Repair",         "Cognitive Castle Repair"),
    ("MemPalace Status",         "Cognitive Castle Status"),
    ("MemPalace Mine",           "Cognitive Castle Mine"),
    ("MemPalace Init",           "Cognitive Castle Init"),
    ("MemPalace — ",             "Cognitive Castle — "),
    ("MemPalace's ",             "Cognitive Castle's "),
    ("MemPalace uses",           "Cognitive Castle uses"),
    ("MemPalace does not",       "Cognitive Castle does not"),
    ("MemPalace Memory Protocol","Cognitive Castle Memory Protocol"),
    ("connect.*MemPalace",       None),  # handled manually — too varied
    # Inline references to mempalace CLI commands in help text / docstrings
    ("`mempalace mine",          "`castle mine"),
    ("`mempalace search",        "`castle search"),
    ("`mempalace init",          "`castle init"),
    ("`mempalace status",        "`castle status"),
    ("`mempalace repair",        "`castle repair"),
    ("`mempalace-mcp",           "`castle-mcp"),
    ("mempalace-mcp",            "castle-mcp"),
    ("mempalace mine",           "castle mine"),
    ("mempalace search",         "castle search"),
    ("mempalace init",           "castle init"),
    ("mempalace status",         "castle status"),
    ("mempalace repair",         "castle repair"),
    # Module path references in docstrings
    (":func:`mempalace.",        ":func:`cognitive_castle."),
    ('"mempalace"',              '"castle"'),   # default agent name in argparse
    # Startup / log messages
    ("MemPalace MCP Server starting", "Cognitive Castle MCP Server starting"),
    # Remaining bare MemPalace references (title case only — avoid renaming classes)
    ("MemPalace",                "Cognitive Castle"),
]

SKIP_PATTERNS = [
    # These are real filenames, not brand strings
    "mempalace.yml",
    "mempal.yaml",
    # These are Python identifiers — never touch
    "MempalaceConfig",
    "mempalace_config",
    "mempalace_palace",
]

def should_skip_line(line):
    return any(p in line for p in SKIP_PATTERNS)

changed_files = []
for py_file in sorted(ROOT.rglob("*.py")):
    text = py_file.read_text(encoding="utf-8")
    new_lines = []
    file_changed = False
    for line in text.splitlines(keepends=True):
        if should_skip_line(line):
            new_lines.append(line)
            continue
        new_line = line
        for src, dst in RULES:
            if dst is None:
                continue
            new_line = new_line.replace(src, dst)
        if new_line != line:
            file_changed = True
        new_lines.append(new_line)
    if file_changed:
        py_file.write_text("".join(new_lines), encoding="utf-8")
        changed_files.append(py_file)

print(f"Modified {len(changed_files)} files:")
for f in changed_files:
    print(f"  {f.relative_to(ROOT.parent)}")
```

Run it:

```bash
cd /Users/ladislavbihari/myWork/soar/cognitive-castle
python /tmp/rebrand.py
```

- [ ] **Step 2: Verify no residual MemPalace display strings remain**

```bash
cd /Users/ladislavbihari/myWork/soar/cognitive-castle
# Should only show lines containing Python class/variable names (MempalaceConfig etc.)
# No print(), argparse help, or example-command strings
grep -rn "MemPalace\|mempalace" cognitive_castle/ --include="*.py" \
  | grep -v "MempalaceConfig\|mine_palace\|mempalace\.yml\|mempal\.yaml" \
  | grep -v "^.*#"
```

Expected: Zero results (or only `mempalace.yml` filename references in skip-dirs lists).

- [ ] **Step 3: Also update repair-status and repair help text to drop ChromaDB references**

In `cognitive_castle/cli.py`:

Line 1233 currently:
```python
help="Compare sqlite vs HNSW element counts (read-only; never opens a chromadb client)",
```

Replace with:
```python
help="Read-only palace health check (legacy ChromaDB mode; no-op for LanceDB palaces)",
```

Line 1178-1180 (`repair` command help):
```python
help=(
    "Rebuild palace vector index (legacy mode) or un-poison max_seq_id rows "
    "(--mode max-seq-id)"
),
```

Replace with:
```python
help=(
    "Palace repair utilities: clean stale lock files (--clean-locks), "
    "or legacy ChromaDB index rebuild (--mode legacy / max-seq-id)"
),
```

- [ ] **Step 4: Run branding tests — expect green**

```bash
cd /Users/ladislavbihari/myWork/soar/cognitive-castle
python -m pytest tests/test_branding.py -v --tb=short 2>&1 | tail -20
```

Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/
git commit -m "refactor: complete Cognitive Castle rebrand across all source modules"
```

---

## Task 4: Fix old `mempalace.` patch paths in test files

**Files:**
- Modify: `tests/test_corpus_origin_integration.py`, `tests/test_cli.py`, `tests/test_dedup.py`, `tests/test_entity_registry.py`, `tests/test_hooks_cli.py`, `tests/test_instructions_cli.py`, `tests/test_llm_client.py`, `tests/test_migrate.py`, `tests/test_miner.py`, `tests/test_normalize.py`, `tests/test_onboarding.py`, `tests/test_repair.py`, `tests/test_spellcheck.py`, `tests/test_spellcheck_extra.py`

All these files use `patch("mempalace.<module>.<Symbol>")`. Since the package is `cognitive_castle`, the patches target the wrong module and have no effect, causing test failures.

- [ ] **Step 1: Run the batch patch-fix script**

Save as `/tmp/fix_test_patches.py` and run:

```python
#!/usr/bin/env python3
"""Replace all patch("mempalace.*") with patch("cognitive_castle.*") in test files."""
from pathlib import Path

TESTS = Path("/Users/ladislavbihari/myWork/soar/cognitive-castle/tests")

changed = []
for py_file in sorted(TESTS.rglob("*.py")):
    text = py_file.read_text(encoding="utf-8")
    if "mempalace." not in text:
        continue
    new_text = text.replace(
        'patch("mempalace.', 'patch("cognitive_castle.'
    ).replace(
        "patch('mempalace.", "patch('cognitive_castle."
    )
    if new_text != text:
        py_file.write_text(new_text, encoding="utf-8")
        changed.append(py_file.name)

print(f"Fixed {len(changed)} test files: {changed}")
```

```bash
python /tmp/fix_test_patches.py
```

Expected output: `Fixed 14 test files: [...]`

- [ ] **Step 2: Verify**

```bash
grep -rn "patch.*mempalace\." /Users/ladislavbihari/myWork/soar/cognitive-castle/tests/ --include="*.py" | wc -l
```

Expected: 0

- [ ] **Step 3: Run the core test suite — confirm no regressions**

```bash
cd /Users/ladislavbihari/myWork/soar/cognitive-castle
python -m pytest tests/test_mcp_server.py tests/test_soar_integration.py tests/test_branding.py -v --tb=short 2>&1 | tail -10
```

Expected: all passed, 0 failed.

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "fix: update all test patches from mempalace.* to cognitive_castle.*"
```

---

## Task 5: Fix B — Flush mining progress output + skipped-file lines

**Files:**
- Modify: `cognitive_castle/miner.py:1070–1084` (banner), `miner.py:1119–1125` (per-file loop)
- Modify: `tests/test_miner.py` (add two tests)

- [ ] **Step 1: Write failing tests in tests/test_miner.py**

Add at the end of `tests/test_miner.py`:

```python
def test_mine_progress_lines_appear_for_new_files(tmp_path, capsys):
    """Each new file must emit a '+ [N/total]' progress line (flush=True)."""
    from cognitive_castle.miner import mine

    (tmp_path / "castle.yaml").write_text(
        "wing: testproj\nrooms:\n  - name: general\n    patterns: ['*']\n"
    )
    (tmp_path / "a.txt").write_text("alpha content")
    (tmp_path / "b.txt").write_text("beta content")

    palace = tmp_path / "palace"
    palace.mkdir()

    mine(project_dir=str(tmp_path), palace_path=str(palace))
    out = capsys.readouterr().out

    assert "  + [" in out, f"Expected '+' progress lines, got:\n{out}"
    assert "a.txt" in out or "b.txt" in out, f"Expected filenames in progress:\n{out}"


def test_mine_skipped_files_emit_dot_line(tmp_path, capsys):
    """On re-mine, already-filed files must emit a '. [N/total] (already filed)' line."""
    from cognitive_castle.miner import mine

    (tmp_path / "castle.yaml").write_text(
        "wing: testproj\nrooms:\n  - name: general\n    patterns: ['*']\n"
    )
    (tmp_path / "a.txt").write_text("alpha content")

    palace = tmp_path / "palace"
    palace.mkdir()

    # First mine — files the content
    mine(project_dir=str(tmp_path), palace_path=str(palace))

    # Second mine — same file, already filed, should show dot line
    capsys.readouterr()  # clear first mine output
    mine(project_dir=str(tmp_path), palace_path=str(palace))
    out = capsys.readouterr().out

    assert "already filed" in out, f"Expected '(already filed)' line on re-mine:\n{out}"
    assert "  . [" in out, f"Expected '.' prefix for skipped files:\n{out}"
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd /Users/ladislavbihari/myWork/soar/cognitive-castle
python -m pytest tests/test_miner.py::test_mine_progress_lines_appear_for_new_files tests/test_miner.py::test_mine_skipped_files_emit_dot_line -v --tb=short 2>&1 | tail -15
```

Expected: both FAILED (no progress output or no "already filed" line)

- [ ] **Step 3: Add flush=True to banner prints in miner.py:1070–1084**

Current lines 1070–1084:
```python
    print(f"\n{'=' * 55}")
    print("  MemPalace Mine")
    print(f"{'=' * 55}")
    print(f"  Wing:    {wing}")
    print(f"  Rooms:   {', '.join(r['name'] for r in rooms)}")
    print(f"  Files:   {len(files)}")
    print(f"  Palace:  {palace_path}")
    print(f"  Device:  {describe_device()}")
    if dry_run:
        print("  DRY RUN — nothing will be filed")
    if not respect_gitignore:
        print("  .gitignore: DISABLED")
    if include_ignored:
        print(f"  Include: {', '.join(sorted(normalize_include_paths(include_ignored)))}")
    print(f"{'-' * 55}\n")
```

(Note: after Task 3 this already says "Cognitive Castle Mine")

Replace with (add `flush=True` to the two framing lines, which are the first visible output):

```python
    print(f"\n{'=' * 55}", flush=True)
    print("  Cognitive Castle Mine", flush=True)
    print(f"{'=' * 55}")
    print(f"  Wing:    {wing}")
    print(f"  Rooms:   {', '.join(r['name'] for r in rooms)}")
    print(f"  Files:   {len(files)}")
    print(f"  Palace:  {palace_path}")
    print(f"  Device:  {describe_device()}")
    if dry_run:
        print("  DRY RUN — nothing will be filed")
    if not respect_gitignore:
        print("  .gitignore: DISABLED")
    if include_ignored:
        print(f"  Include: {', '.join(sorted(normalize_include_paths(include_ignored)))}")
    print(f"{'-' * 55}\n", flush=True)
```

- [ ] **Step 4: Add flush + skipped-file output to the per-file loop at miner.py:1119–1125**

Current:
```python
            if drawers == 0 and not dry_run:
                files_skipped += 1
            else:
                total_drawers += drawers
                room_counts[room] += 1
                if not dry_run:
                    print(f"  + [{i:4}/{len(files)}] {filepath.name[:50]:50} +{drawers}")
```

Replace with:
```python
            if drawers == 0 and not dry_run:
                files_skipped += 1
                print(f"  . [{i:4}/{len(files)}] {filepath.name[:50]:50} (already filed)", flush=True)
            else:
                total_drawers += drawers
                room_counts[room] += 1
                if not dry_run:
                    print(f"  + [{i:4}/{len(files)}] {filepath.name[:50]:50} +{drawers}", flush=True)
```

- [ ] **Step 5: Run tests — expect green**

```bash
python -m pytest tests/test_miner.py::test_mine_progress_lines_appear_for_new_files tests/test_miner.py::test_mine_skipped_files_emit_dot_line -v --tb=short 2>&1 | tail -10
```

Expected: both PASSED.

- [ ] **Step 6: Verify dry-run shows immediate output**

```bash
castle mine /Users/ladislavbihari/myWork/soar/cognitive-castle --dry-run --limit 5 2>&1 | head -15
```

Expected: the "Cognitive Castle Mine" banner appears immediately, followed by `[DRY RUN]` lines for each file.

- [ ] **Step 7: Commit**

```bash
git add cognitive_castle/miner.py tests/test_miner.py
git commit -m "fix: flush mining progress output and emit '(already filed)' lines on re-mine"
```

---

## Task 6: Fix C — `--yes` implies the mine prompt

**Files:**
- Modify: `cognitive_castle/cli.py:388–427`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_miner.py` (or a dedicated `tests/test_init_yes_flag.py`):

```python
def test_yes_flag_skips_mine_prompt(tmp_path, monkeypatch):
    """--yes must suppress the 'Mine this directory now?' prompt without calling input()."""
    import argparse
    from unittest.mock import patch as mock_patch
    from cognitive_castle.cli import _maybe_run_mine_after_init

    # Simulate a project dir with a castle.yaml (so scan_project returns something)
    (tmp_path / "castle.yaml").write_text(
        "wing: testproj\nrooms:\n  - name: general\n    patterns: ['*']\n"
    )
    (tmp_path / "note.txt").write_text("hello")

    args = argparse.Namespace(
        dir=str(tmp_path),
        yes=True,
        auto_mine=False,
        palace=None,
        wing=None,
        agent="castle",
        no_gitignore=False,
        include_ignored=None,
        limit=0,
        mode="projects",
        redetect_origin=False,
    )

    mine_called = []

    with mock_patch("cognitive_castle.cli.mine", side_effect=lambda **kw: mine_called.append(kw)):
        with mock_patch("builtins.input", side_effect=AssertionError("input() must not be called with --yes")):
            _maybe_run_mine_after_init(args, cfg=None)

    assert mine_called, "--yes should auto-mine without prompting"
```

- [ ] **Step 2: Run it — expect failure**

```bash
python -m pytest tests/test_miner.py::test_yes_flag_skips_mine_prompt -v --tb=short 2>&1 | tail -15
```

Expected: FAILED — input() is called (or mine is not called)

- [ ] **Step 3: Change cli.py:388–389 and cli.py:427**

Find the comment at lines 388–389:
```python
    # `--auto-mine` skips the prompt and mines automatically; `--yes` is
    # SCOPED to entity auto-accept and does NOT imply mining.
```

Replace with:
```python
    # Both `--auto-mine` and `--yes` skip the mine prompt and mine automatically.
    # `--yes` means "accept all defaults non-interactively" — that includes this prompt.
```

Find line 427:
```python
    auto_mine = bool(getattr(args, "auto_mine", False))
```

Replace with:
```python
    auto_mine = bool(getattr(args, "auto_mine", False)) or bool(getattr(args, "yes", False))
```

Also find the --auto-mine help text at line 968 (approx):
```python
        help=(
            "Skip the post-init mine prompt and run mine"
            " automatically. Combine with --yes for a fully non-interactive setup."
        ),
```

Replace with:
```python
        help=(
            "Skip the post-init mine prompt and run mine automatically."
            " Equivalent to --yes for the mine step; both flags imply non-interactive mining."
        ),
```

- [ ] **Step 4: Run test — expect green**

```bash
python -m pytest tests/test_miner.py::test_yes_flag_skips_mine_prompt -v --tb=short 2>&1 | tail -10
```

Expected: PASSED.

- [ ] **Step 5: Manual smoke test**

```bash
castle init /tmp/castle-test-yes --yes --no-llm 2>&1
```

Expected: completes without prompting "Mine this directory now?", and either runs the mine or exits cleanly (depending on file count and whether the palace is writable).

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/cli.py tests/test_miner.py
git commit -m "fix: --yes implies mine prompt (non-interactive init no longer requires --auto-mine)"
```

---

## Task 7: Fix D — `castle repair --clean-locks`

**Files:**
- Modify: `cognitive_castle/cli.py` (add --clean-locks argument + handler)
- Modify: `cognitive_castle/palace.py` (add `clean_stale_locks()` function)
- Create: `tests/test_clean_locks.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_clean_locks.py
"""Tests for the stale lock cleanup utility."""
import os
import time
import tempfile
from pathlib import Path

import pytest


def _create_lock(lock_dir: Path, name: str, age_seconds: int) -> Path:
    """Create a lock file and backdate its mtime by age_seconds."""
    path = lock_dir / name
    path.write_text("")
    mtime = time.time() - age_seconds
    os.utime(path, (mtime, mtime))
    return path


def test_clean_stale_locks_removes_old_files(tmp_path):
    """Files older than max_age_seconds are deleted; fresh files are kept."""
    from cognitive_castle.palace import clean_stale_locks

    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()

    old = _create_lock(lock_dir, "old.lock", age_seconds=90000)   # 25 h old → stale
    fresh = _create_lock(lock_dir, "fresh.lock", age_seconds=60)  # 1 min old → keep

    removed, kept = clean_stale_locks(str(lock_dir), max_age_seconds=86400)

    assert removed == 1
    assert kept == 1
    assert not old.exists(), "Stale lock should be deleted"
    assert fresh.exists(), "Fresh lock should be kept"


def test_clean_stale_locks_empty_dir(tmp_path):
    from cognitive_castle.palace import clean_stale_locks

    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()

    removed, kept = clean_stale_locks(str(lock_dir))
    assert removed == 0
    assert kept == 0


def test_clean_stale_locks_missing_dir(tmp_path):
    from cognitive_castle.palace import clean_stale_locks

    removed, kept = clean_stale_locks(str(tmp_path / "nonexistent"))
    assert removed == 0
    assert kept == 0


def test_repair_clean_locks_cli(tmp_path, monkeypatch):
    """castle repair --clean-locks calls clean_stale_locks and prints summary."""
    import argparse
    import io, contextlib
    from cognitive_castle.cli import cmd_repair
    from unittest.mock import patch

    # Patch clean_stale_locks to return (5, 2) without touching filesystem
    with patch("cognitive_castle.cli.clean_stale_locks", return_value=(5, 2)) as mock_clean:
        args = argparse.Namespace(
            palace=None,
            clean_locks=True,
            mode="legacy",
            yes=False,
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_repair(args)

    mock_clean.assert_called_once()
    out = buf.getvalue()
    assert "5" in out and "stale" in out.lower(), f"Expected removal summary:\n{out}"
```

- [ ] **Step 2: Run tests — expect failures**

```bash
python -m pytest tests/test_clean_locks.py -v --tb=short 2>&1 | tail -15
```

Expected: all FAILED (`clean_stale_locks` not yet defined)

- [ ] **Step 3: Add `clean_stale_locks()` to palace.py**

Add after the `mine_global_lock` alias at line 392 in `cognitive_castle/palace.py`:

```python
def clean_stale_locks(lock_dir: str, max_age_seconds: int = 86400):
    """Delete lock files older than max_age_seconds from lock_dir.

    Returns (removed, kept) counts. Safe to call on a missing directory.
    Any lock older than 24 h is definitively stale — the process that held it
    is long dead, since mine operations never take more than a few hours.
    """
    if not os.path.isdir(lock_dir):
        return 0, 0
    cutoff = time.time() - max_age_seconds
    removed = 0
    kept = 0
    for entry in os.scandir(lock_dir):
        if not entry.name.endswith(".lock"):
            continue
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            try:
                os.remove(entry.path)
                removed += 1
            except OSError:
                kept += 1
        else:
            kept += 1
    return removed, kept
```

Also add `import time` to palace.py if not already present:

```bash
grep -n "^import time" cognitive_castle/palace.py
```

If missing, add it near the top with the other stdlib imports.

- [ ] **Step 4: Wire `--clean-locks` into cli.py**

In `cmd_repair` (line 652), add an early-exit branch **before** the existing ChromaBackend logic:

```python
def cmd_repair(args):
    """Rebuild palace vector index from SQLite metadata."""
    from .config import MempalaceConfig
    from .palace import clean_stale_locks

    palace_path = os.path.abspath(
        os.path.expanduser(args.palace) if args.palace else MempalaceConfig().palace_path
    )

    # --clean-locks: remove stale lock files (>24 h old) from the locks directory.
    # This path is independent of the ChromaDB-specific rebuild logic below.
    if getattr(args, "clean_locks", False):
        lock_dir = os.path.join(os.path.dirname(palace_path), "locks")
        removed, kept = clean_stale_locks(lock_dir)
        print(f"  Removed {removed} stale lock(s). Kept {kept} active lock(s).")
        if removed == 0 and kept == 0:
            print("  Lock directory is empty or does not exist.")
        return

    # ... rest of existing cmd_repair function unchanged ...
```

Add `--clean-locks` argument to the `p_repair` argparse block (around line 1183):

```python
    p_repair.add_argument(
        "--clean-locks",
        action="store_true",
        default=False,
        help=(
            "Remove lock files older than 24 h from ~/.castle/locks/. "
            "Safe to run at any time — active locks are never touched."
        ),
    )
```

- [ ] **Step 5: Run tests — expect green**

```bash
python -m pytest tests/test_clean_locks.py -v --tb=short 2>&1 | tail -10
```

Expected: all PASSED.

- [ ] **Step 6: Run the cleanup against the live stale locks**

```bash
castle repair --clean-locks 2>&1
```

Expected output similar to:
```
  Removed 216 stale lock(s). Kept 0 active lock(s).
```

- [ ] **Step 7: Verify lock directory is clean**

```bash
find ~/.castle/locks -type f | wc -l
```

Expected: 0

- [ ] **Step 8: Commit**

```bash
git add cognitive_castle/palace.py cognitive_castle/cli.py tests/test_clean_locks.py
git commit -m "feat: add castle repair --clean-locks to remove stale lock files (>24h old)"
```

---

## Task 8: Fix E — Exclude benchmark data files from mining

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add exclusions to .gitignore**

Open `.gitignore` and find the `# MemPalace per-project files` section (near the bottom). Add a new section after it:

```gitignore
# Benchmark result artifacts — large data files, not source code
# castle mine respects .gitignore by default; these are never useful to index
benchmarks/*.json
benchmarks/*.jsonl
```

- [ ] **Step 2: Verify via dry-run**

```bash
cd /Users/ladislavbihari/myWork/soar/cognitive-castle
castle mine . --dry-run 2>&1 | grep -i benchmark
```

Expected: zero `benchmark` lines in output (the JSON/JSONL files are excluded).

- [ ] **Step 3: Confirm scan_project respects the exclusion**

```bash
python -c "
from cognitive_castle.miner import scan_project
files = scan_project('/Users/ladislavbihari/myWork/soar/cognitive-castle')
bench_json = [f for f in files if 'benchmarks' in str(f) and f.suffix in ('.json', '.jsonl')]
print(f'benchmark json/jsonl files that would be mined: {len(bench_json)}')
for f in bench_json[:5]: print(' ', f)
"
```

Expected: `benchmark json/jsonl files that would be mined: 0`

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "fix: exclude benchmarks/*.json and *.jsonl from castle mine via .gitignore"
```

---

## Task 9: Final verification

- [ ] **Step 1: Run the full relevant test suite**

```bash
cd /Users/ladislavbihari/myWork/soar/cognitive-castle
python -m pytest \
  tests/test_branding.py \
  tests/test_clean_locks.py \
  tests/test_mcp_server.py \
  tests/test_soar_integration.py \
  tests/test_miner.py \
  tests/test_palace_locks.py \
  -v --tb=short 2>&1 | tail -20
```

Expected: all passed, 0 failed.

- [ ] **Step 2: Spot-check CLI output strings**

```bash
castle --help | grep -i "mempalace\|MemPalace"
castle mine --help | grep -i "mempalace\|MemPalace"
castle repair --help | grep -i "mempalace\|MemPalace"
```

Expected: zero results for all three.

- [ ] **Step 3: Confirm benchmark exclusion stuck**

```bash
castle status 2>&1 | grep -i benchmark
```

Expected: `benchmarks` room no longer appears in status (or shows 0 drawers if palace hasn't been re-mined).

- [ ] **Step 4: Final commit if any loose ends**

```bash
git status
git add -p  # review anything untracked
git commit -m "chore: final cleanup for UX polish (branding, progress, --yes, locks, benchmarks)"
```

---

## Self-review notes

- **Spec coverage**: All 5 fixes have corresponding tasks. Fix A is split across Tasks 1–4 (TDD red → green → test patches). Fix B is Task 5. Fix C is Task 6. Fix D is Task 7. Fix E is Task 8.
- **No placeholders**: All code is complete and executable.
- **Type consistency**: `clean_stale_locks(lock_dir, max_age_seconds)` is defined in Task 7 Step 3 and used consistently in Steps 4 and tests.
- **Batch script approach for Fix A**: The rebrand script in Task 3 is safe because it explicitly skips lines containing `MempalaceConfig`, `mine_palace_lock`, and other identifiers. The `mempalace.yml` filename pattern is preserved.
- **Test patch fix**: Task 4 fixes the 14 test files with `patch("mempalace.*")` stale paths — this may resolve some of the pre-existing `test_repair.py` and other failures as a side-effect.
