# Cognitive Castle — UX Polish: 5 Fixes

**Date:** 2026-05-05
**Branch target:** develop

## Background

Five concrete UX problems found during a live session with the tool:

1. CLI and output still say "MemPalace" throughout — the rebrand to Cognitive Castle is incomplete
2. `castle mine` is silent while running — buffered output means no progress until done
3. `--yes` does not suppress the "Mine this directory now?" prompt — requires `--yes --auto-mine` which is non-obvious
4. 216+ stale lock files accumulate in `~/.castle/locks/` from test runs — can block a fresh mine
5. Benchmark data files (`.json`/`.jsonl`) in `benchmarks/` get mined into the palace — 21,004 of 24,988 drawers were irrelevant benchmark rows

---

## Fix A — Rebrand: "MemPalace" → "Cognitive Castle"

### Scope

41 Python files under `cognitive_castle/` contain `"MemPalace"` or `"mempalace"` display strings. Every user-facing string (CLI help, status banners, error messages, progress output, example commands) must read "Cognitive Castle" or `castle`.

### Changes

- All `print(...)` banners: `MemPalace Mine` → `Cognitive Castle Mine`, `MemPalace Status` → `Cognitive Castle Status`, etc.
- Example commands in help text: `mempalace mine` → `castle mine`, `mempalace search` → `castle search`
- `--agent` default value: `"mempalace"` → `"castle"`
- `repair-status` help: remove ChromaDB/HNSW references (already migrated to LanceDB)
- `repair` command description: remove ChromaDB migration language
- `migrate` command description: update to reflect LanceDB is now the default
- Entity detector false positive: the string `"MemPalace"` in Python source triggers entity detection; removing it as a display string reduces noise
- Keep `mempalace` as a silent entry-point alias in `pyproject.toml` for backward compat — users with existing shell aliases won't break

### What does NOT change

- Internal Python identifiers, variable names, module names — only user-visible strings
- The `mempalace` CLI entry point in `pyproject.toml` — kept as alias

---

## Fix B — Mining Progress Visibility

### Problem

`castle mine` on 256 files runs for 5+ minutes with zero output. Two root causes:

1. `print(...)` at `miner.py:1125` is buffered — Python buffers stdout when piped, so nothing appears until the process ends
2. Already-filed files are silently skipped — a re-mine of an up-to-date palace produces no output at all

### Fix

**Part 1 — flush existing progress lines**

Add `flush=True` to the per-file progress print at `miner.py:1125`:

```python
print(f"  + [{i:4}/{len(files)}] {filepath.name[:50]:50} +{drawers}", flush=True)
```

Also add `flush=True` to the header banner prints so they appear immediately when the command starts.

**Part 2 — output for skipped files**

When a file is already filed and skipped, emit a compact line at the same position in the loop:

```python
print(f"  . [{i:4}/{len(files)}] {filepath.name[:50]:50} (already filed)", flush=True)
```

A dot prefix (`·`) visually distinguishes skipped from filed (`+`), so a re-mine of a fully up-to-date palace shows progress without noise.

**No new dependency** — no tqdm, no third-party progress library.

---

## Fix C — `--yes` Implies Mine Prompt

### Problem

`castle init --yes` auto-accepts entities but still interactively asks:

```
Mine this directory now? [Y/n]
```

Non-interactive callers (CI, scripts, other tools) need `--yes --auto-mine` to skip it. `--auto-mine` is not surfaced prominently and the combination is undiscoverable.

### Fix

In `cli.py`, change the `_maybe_mine_after_init` function so that `args.yes` also suppresses the mine prompt (treating it as "yes"):

```python
# Before
auto_mine = bool(getattr(args, "auto_mine", False))

# After
auto_mine = bool(getattr(args, "auto_mine", False)) or bool(getattr(args, "yes", False))
```

Remove the comment at line 415 that explicitly says `--yes` does NOT imply this.

`--auto-mine` stays as an explicit flag. Its behaviour is unchanged — this fix simply makes `--yes` equivalent.

---

## Fix D — Stale Lock File Accumulation

### Problem

Tests that ran before the HOME-redirect fixture was in place left 216 lock files in `~/.castle/locks/`. New test runs (which redirect HOME to a tempdir) no longer pollute `~/.castle/locks/`, but the 216 legacy files remain and each one takes a slot that the lock manager scans.

Additionally, if a `castle mine` process crashes mid-run, it can leave a stale lock that blocks future runs until manually deleted.

### Fix

**Part 1 — `castle repair --clean-locks`**

Add a `--clean-locks` mode to the existing `repair` command. It:

1. Lists all files in `{palace_root}/../locks/` (i.e., `~/.castle/locks/`)
2. Deletes any lock file whose mtime is older than 24 hours
3. Prints a count: `Removed N stale lock(s). Kept M active lock(s).`

This is safe because any lock that's been sitting for >24 h is definitively stale (the mine process that held it is long dead).

**Part 2 — one-time cleanup**

Run `castle repair --clean-locks` once as part of this implementation to clear the 216 existing stale files.

**No changes to conftest.py** — the HOME-redirect fixture already prevents new pollution from tests.

---

## Fix E — Benchmark Data Excluded from Mining

### Problem

`benchmarks/` contains large JSON/JSONL result files (e.g., `lme_split_50_450.json`, `results_*.json`, `results_*.jsonl`). When a user runs `castle mine` on the cognitive-castle project, these files get chunked and filed — 21,004 drawers of irrelevant benchmark data that dominate every search result.

### Fix

Add the benchmark data files to `.gitignore`:

```gitignore
# Benchmark result artifacts — not source code, not mined into palace
benchmarks/*.json
benchmarks/*.jsonl
```

`castle mine` already respects `.gitignore` (unless `--no-gitignore` is passed), so this exclusion is automatic with no code change.

Also update `castle.yaml` (the init-generated config for the cognitive-castle repo) with a comment marking the benchmarks room as data-heavy:

```yaml
# benchmarks/ room contains large result datasets — not useful to mine
# Run with --no-gitignore only if you specifically need those files indexed
```

---

## Testing

Each fix has a clear verification:

| Fix | Verification |
|-----|-------------|
| A (rebrand) | `castle --help`, `castle mine --help`, `castle status` contain no "MemPalace" strings |
| B (progress) | Run `castle mine --dry-run` on a small dir — each file emits a flushed line immediately |
| C (`--yes`) | `castle init <dir> --yes --no-llm` completes without prompting; mine runs if dir is small |
| D (locks) | `castle repair --clean-locks` runs clean; `~/.castle/locks/` contains 0 files after |
| E (benchmarks) | `castle mine <cognitive-castle-dir>` followed by `castle status` shows 0 drawers in benchmarks room |

Existing tests must continue to pass (no regressions).

---

## Out of Scope

- Fix 5 pre-existing test failures (spellcheck, repair, room_detector, tunnel hyphenation, version) — separate ticket
- Qdrant backend
- Multi-device sync
- Multilingual embeddings
