# bge-m3 Unblock + Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship documentation + a paired-CLI-flag UX + a regression test that make `BAAI/bge-m3` a usable opt-in embedder for Cognitive Castle. No default change.

**Architecture:** Zero new modules. Extends `cmd_reindex` (`cli.py:629-672`) with `--embedder MODEL_NAME` and `--embedder-dim N` flags that override the corresponding env vars before mining. Adds a slow regression test, an argparse pair-validation test, and two doc surfaces (README + CLAUDE.md). The bge-m3 hang is already solved by the SDP-disable workaround at `embedding.py:92-100` — this PR documents, tests, and exposes the capability.

**Tech Stack:** Python 3.12, sentence-transformers, LanceDB, argparse, pytest. No new dependencies.

**Spec:** [`docs/superpowers/specs/2026-05-12-bge-m3-unblock-design.md`](../specs/2026-05-12-bge-m3-unblock-design.md) (commit `a4876b60`).

**File map (4 files, ~95 LOC):**

| File | Responsibility | Tasks |
|---|---|---|
| `cognitive_castle/cli.py` | Add paired flags + validation in `cmd_reindex` | Tasks 2, 3 |
| `tests/test_cli.py` | Argparse pair-validation regression test | Task 2 |
| `tests/test_embedding.py` | Slow regression test that bge-m3 still loads | Task 4 |
| `CLAUDE.md` | Note bge-m3 as supported alternative in pipeline diagram | Task 5 |
| `README.md` | "Going further: better recall with bge-m3" subsection after Quickstart | Task 6 |

---

## Task 1: Create feature branch

**Files:** none (git only)

- [ ] **Step 1: Confirm we're on `develop` and the tree is clean**

Run:
```bash
git status
git log --oneline -3
```

Expected:
- `On branch develop`
- Working tree clean (the `test_env/` untracked dir from prior session is OK to ignore)
- Latest commit is the spec commit `a4876b60` or later

- [ ] **Step 2: Create + switch to feature branch**

Run:
```bash
git checkout -b feat/bge-m3-unblock
```

Expected: `Switched to a new branch 'feat/bge-m3-unblock'`

- [ ] **Step 3: Verify branch**

Run:
```bash
git branch --show-current
```

Expected: `feat/bge-m3-unblock`

No commit yet — branch creation is not committable on its own.

---

## Task 2: Argparse pair-validation test (TDD red)

**Files:**
- Modify: `tests/test_cli.py` (append new test at end of file)

The spec requires `--embedder` and `--embedder-dim` to be passed together — passing only one is a usage error. We write the failing test first, then make it pass in Tasks 3 and 4.

- [ ] **Step 1: Append the failing test to `tests/test_cli.py`**

Append at end of file:

```python
def test_reindex_rejects_unpaired_embedder_flags(monkeypatch, capsys, tmp_path):
    """`castle reindex --embedder X` without --embedder-dim must be a usage error.

    The CLI exposes two paired flags so users can't accidentally set the model
    without the dim (which would later fail with a cryptic LanceDB cast error
    deep in the miner). Validation runs at the top of cmd_reindex BEFORE any
    filesystem work happens.
    """
    import argparse
    import pytest
    from cognitive_castle.cli import cmd_reindex

    # Build a Namespace that mirrors what argparse would produce for:
    #   castle reindex --palace <p> --sources <s> --embedder BAAI/bge-m3 --yes
    # (note: --embedder-dim is intentionally absent → embedder_dim=None)
    args = argparse.Namespace(
        palace=str(tmp_path / "palace"),
        sources=[str(tmp_path / "src")],
        yes=True,
        embedder="BAAI/bge-m3",
        embedder_dim=None,
    )

    # Ensure no stale env vars influence the test
    monkeypatch.delenv("CASTLE_EMBEDDER_MODEL", raising=False)
    monkeypatch.delenv("CASTLE_EMBEDDER_DIM", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        cmd_reindex(args)

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "--embedder and --embedder-dim must be passed together" in captured.err


def test_reindex_rejects_unpaired_dim_flag(monkeypatch, capsys, tmp_path):
    """Reverse case: --embedder-dim without --embedder is also a usage error."""
    import argparse
    import pytest
    from cognitive_castle.cli import cmd_reindex

    args = argparse.Namespace(
        palace=str(tmp_path / "palace"),
        sources=[str(tmp_path / "src")],
        yes=True,
        embedder=None,
        embedder_dim=1024,
    )

    monkeypatch.delenv("CASTLE_EMBEDDER_MODEL", raising=False)
    monkeypatch.delenv("CASTLE_EMBEDDER_DIM", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        cmd_reindex(args)

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "--embedder and --embedder-dim must be passed together" in captured.err
```

- [ ] **Step 2: Run the new tests and confirm they FAIL**

Run:
```bash
pytest tests/test_cli.py::test_reindex_rejects_unpaired_embedder_flags tests/test_cli.py::test_reindex_rejects_unpaired_dim_flag -v
```

Expected: Both tests FAIL. The failure mode will be one of:
- `AttributeError: 'Namespace' object has no attribute 'embedder'` (if Namespace access fails)
- `Failed: DID NOT RAISE <class 'SystemExit'>` (if cmd_reindex runs through without the new validation)

Either failure mode is the right kind — it proves the test sees the gap.

No commit yet — we commit the test together with the implementation that makes it pass in Task 4.

---

## Task 3: Add `--embedder` and `--embedder-dim` argparse flags

**Files:**
- Modify: `cognitive_castle/cli.py:1128-1143` (add two new `p_reindex.add_argument` calls)

- [ ] **Step 1: Add the two new flags**

In `cognitive_castle/cli.py`, find the existing `p_reindex` block (around line 1128-1143). After the existing `p_reindex.add_argument("--yes", ...)` call (line 1139-1143), append:

```python
    p_reindex.add_argument(
        "--embedder",
        default=None,
        help=(
            "Override embedder model for this reindex run only (sets "
            "CASTLE_EMBEDDER_MODEL). MUST be passed together with --embedder-dim. "
            "See README 'Going further: better recall with bge-m3' for known "
            "model→dim pairs."
        ),
    )
    p_reindex.add_argument(
        "--embedder-dim",
        type=int,
        default=None,
        help=(
            "Override embedder output dim for this reindex run only (sets "
            "CASTLE_EMBEDDER_DIM). MUST be passed together with --embedder."
        ),
    )
```

- [ ] **Step 2: Verify the help text appears**

Run:
```bash
castle reindex --help 2>&1 | grep -E "embedder|dim"
```

Expected: both `--embedder MODEL_NAME` and `--embedder-dim N` flags appear in the help output, each with the help text above. (argparse normalizes `--embedder-dim` to `args.embedder_dim` automatically.)

No commit yet — the validation logic still has to be added in Task 4 before the tests will pass.

---

## Task 4: Add paired-flag validation + env override in `cmd_reindex` (TDD green)

**Files:**
- Modify: `cognitive_castle/cli.py:629-672` (insert validation + env override at the top of `cmd_reindex`)

- [ ] **Step 1: Insert validation block at top of `cmd_reindex`**

In `cognitive_castle/cli.py`, find `def cmd_reindex(args) -> None:` at line 629. Immediately after the docstring (which ends at line 638 with `"""`), insert:

```python
    # Paired CLI overrides — must be both or neither.
    # Setting only one would later fail with a cryptic LanceDB cast error deep
    # in the miner. Validate up front and exit cleanly on misuse.
    embedder = getattr(args, "embedder", None)
    embedder_dim = getattr(args, "embedder_dim", None)
    if (embedder is None) != (embedder_dim is None):
        print(
            "--embedder and --embedder-dim must be passed together",
            file=sys.stderr,
        )
        sys.exit(2)
    if embedder is not None:
        os.environ["CASTLE_EMBEDDER_MODEL"] = embedder
        os.environ["CASTLE_EMBEDDER_DIM"] = str(embedder_dim)
```

- [ ] **Step 2: Verify `sys` and `os` imports exist at the top of `cli.py`**

Run:
```bash
head -30 /home/lbihari/cognitive-castle/cognitive_castle/cli.py | grep -E "^import (sys|os)$|^import os, sys|^import sys, os"
```

Expected: both `import os` and `import sys` present. If `import sys` is missing, add it to the imports block at the top of the file (near the existing `import os`).

- [ ] **Step 3: Run the pair-validation tests and confirm they PASS**

Run:
```bash
pytest tests/test_cli.py::test_reindex_rejects_unpaired_embedder_flags tests/test_cli.py::test_reindex_rejects_unpaired_dim_flag -v
```

Expected: both tests PASS (2 passed).

- [ ] **Step 4: Run the full test suite to confirm no regression**

Run:
```bash
pytest tests/ -v --ignore=tests/benchmarks
```

Expected: same number of passing tests as before + 2 new tests passing. Pre-existing failures (per project memory: "CI-UNSTABLE OK for documented pre-existing failures") are acceptable.

- [ ] **Step 5: Lint check**

Run:
```bash
ruff check cognitive_castle/cli.py tests/test_cli.py && ruff format --check cognitive_castle/cli.py tests/test_cli.py
```

Expected: no errors.

- [ ] **Step 6: Commit Tasks 2–4 together**

```bash
git add cognitive_castle/cli.py tests/test_cli.py
git commit -m "$(cat <<'EOF'
feat(cli): add --embedder + --embedder-dim flags to castle reindex

Paired flags must be passed together; passing only one raises sys.exit(2)
with a clear stderr message. When passed, both flags override the
corresponding env vars (CASTLE_EMBEDDER_MODEL, CASTLE_EMBEDDER_DIM) for the
duration of the reindex process only — no config-file write.

Enables one-shot migration to bge-m3 (or any HF embedder) without editing
castle.yaml first. Validation prevents the cryptic LanceDB cast error that
would otherwise occur if only the model was changed without updating the dim.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: bge-m3 slow regression test

**Files:**
- Modify: `tests/test_embedding.py` (append new test at end of file)

This test catches future regressions of the SDP-disable workaround. It's marked `@pytest.mark.slow` so it doesn't run in default CI (which would force a 2 GB model download on every run); developers run it explicitly when touching embedder code.

- [ ] **Step 1: Append the test to `tests/test_embedding.py`**

Append at end of file:

```python
@pytest.mark.slow
def test_bge_m3_loads_and_embeds_at_1024_dim():
    """Regression: bge-m3 must load + first-encode without hanging.

    The SDP-disable workaround in embedding._get_model is what makes this
    possible — without it, the first CUDA encode triggers a 3+ minute
    flash-attention JIT compilation. If a future torch upgrade breaks the
    workaround, this test catches it before users hit the hang in production
    reindex.

    Marked @pytest.mark.slow because:
    - First run downloads ~2 GB of model weights
    - Even cached, model load takes ~8s
    Default pytest config excludes -m slow tests.
    """
    from unittest.mock import MagicMock
    import cognitive_castle.embedding as emb

    cfg = MagicMock()
    cfg.embedder_model = "BAAI/bge-m3"
    model = emb._get_model(device="auto", cfg=cfg)
    vecs = model.encode(
        ["hello world", "ahoj jak se mas", "cognitive castle"],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    assert vecs.shape == (3, 1024)
    # L2-normalized: first vector should have unit norm
    assert abs(float((vecs[0] ** 2).sum()) ** 0.5 - 1.0) < 1e-4
```

- [ ] **Step 2: Confirm `pytest` import already exists in the test file**

Run:
```bash
head -3 /home/lbihari/cognitive-castle/tests/test_embedding.py
```

Expected: `import pytest` on line 1. (If not, add it.)

- [ ] **Step 3: Run the new test (downloads ~2 GB on first run)**

Run:
```bash
pytest tests/test_embedding.py::test_bge_m3_loads_and_embeds_at_1024_dim -v -m slow
```

Expected: PASS. Total time ~10s (model load + 3-string encode) on a warm cache; up to several minutes on cold cache for the model download.

If this fails with a CUDA OOM or hang on the implementer's hardware, the bge-m3 capability is not actually unblocked on that environment and the spec's premise needs revisiting. **Do not skip the test.**

- [ ] **Step 4: Confirm the test is excluded from default suite**

Run:
```bash
pytest tests/test_embedding.py -v
```

Expected: the new `test_bge_m3_loads_and_embeds_at_1024_dim` does NOT appear in the run (because default `addopts = "-m 'not benchmark and not slow and not stress'"` filters it).

- [ ] **Step 5: Lint check**

Run:
```bash
ruff check tests/test_embedding.py && ruff format --check tests/test_embedding.py
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add tests/test_embedding.py
git commit -m "$(cat <<'EOF'
test(embedding): slow regression test that bge-m3 loads + embeds at 1024-dim

Marked @pytest.mark.slow so it doesn't run in default CI (2 GB model
download). Catches future regressions of the SDP-disable workaround at
embedding.py:92-100, which is what unblocks bge-m3 on CUDA (otherwise the
first encode triggers a 3+ minute flash-attention JIT compilation hang).

Run explicitly via `pytest -m slow` when touching embedder code.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Update CLAUDE.md embedder references

**Files:**
- Modify: `CLAUDE.md:87` (file tree comment)
- Modify: `CLAUDE.md:179` (retrieval pipeline diagram)

CLAUDE.md mentions `paraphrase-multilingual-MiniLM-L12-v2` in two places. Update both to note that bge-m3 is a supported alternative.

- [ ] **Step 1: Update the file tree comment (line 87)**

Replace the line:
```
├── embedding.py            # Sentence-transformers embedding (paraphrase-multilingual-MiniLM-L12-v2, 384-dim)
```

with:
```
├── embedding.py            # Sentence-transformers embedding (default: paraphrase-multilingual-MiniLM-L12-v2 384-dim; alternative: BAAI/bge-m3 1024-dim via config)
```

- [ ] **Step 2: Update the retrieval pipeline diagram (line 179)**

Replace the line:
```
    │     ├── Dense vector search (paraphrase-multilingual-MiniLM-L12-v2 via LanceDB)
```

with:
```
    │     ├── Dense vector search (paraphrase-multilingual-MiniLM-L12-v2 default, BAAI/bge-m3 supported via config — see README)
```

- [ ] **Step 3: Sanity check (no stale singular references)**

Run:
```bash
grep -n "paraphrase-multilingual-MiniLM" /home/lbihari/cognitive-castle/CLAUDE.md
```

Expected: both updated lines mention bge-m3 alongside MiniLM. No remaining lines claim MiniLM is the only embedder.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(claude.md): mention bge-m3 as supported embedder alternative

CLAUDE.md had two MiniLM-only references (file tree comment + retrieval
pipeline diagram). Both now note bge-m3 as a supported alternative via
config — matches the README "Going further" section landing in the same PR.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Update README — "Going further: better recall with bge-m3"

**Files:**
- Modify: `README.md` (insert new section between line 127 `---` separator and line 129 `## How it works`)

- [ ] **Step 1: Insert the new subsection**

In `README.md`, the existing Quickstart section ends at line 127 (`---`). Immediately after that separator and BEFORE `## How it works` on line 129, insert:

```markdown
## Going further: better recall with bge-m3

Castle ships with `paraphrase-multilingual-MiniLM-L12-v2` (384-dim) as the default embedder — fast, multilingual, modest hardware needs. If you want stronger retrieval (especially for non-English content or fine-grained semantic distinctions), switch to **`BAAI/bge-m3`** (1024-dim). It consistently outperforms MiniLM on MTEB retrieval benchmarks.

**Hardware:** ≈2.3 GB VRAM (NVIDIA / Apple Silicon GPU recommended). Falls back to CPU automatically if VRAM is insufficient, but CPU encoding is significantly slower.

### Migration (two-step)

1. Edit `~/.castle.yaml` (or the palace-local `castle.yaml`) — set **both** keys:

   ```yaml
   embedder_model: BAAI/bge-m3
   embedder_dim: 1024
   ```

2. Reindex:

   ```bash
   castle reindex --palace ~/.castle/palace --sources ~/projects --yes
   ```

### Migration (one-shot — no config edit)

```bash
castle reindex \
  --palace ~/.castle/palace \
  --sources ~/projects \
  --embedder BAAI/bge-m3 \
  --embedder-dim 1024 \
  --yes
```

Both `--embedder` and `--embedder-dim` MUST be passed together; passing only one is a usage error.

### Known model→dim pairs

| `embedder_model` | `embedder_dim` |
|---|---|
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (default) | 384 |
| `BAAI/bge-m3` (recommended for better recall) | 1024 |
| `BAAI/bge-large-en-v1.5` (English-only) | 1024 |

### ⚠️ Forget-to-reindex footgun

If you change `embedder_model` / `embedder_dim` in `castle.yaml` without running `castle reindex`, the next search will fail with a cryptic LanceDB dim-mismatch error like:

```
RuntimeError: query dim(1024) doesn't match the column vector vector dim(384)
```

There's no silent corruption — the system errors loudly — but the error doesn't tell you to reindex. **Always reindex after changing embedder config.** A friendlier error message is tracked as a follow-up PR.

---

```

Note: end the new section with `---` so it visually separates from the next section.

- [ ] **Step 2: Verify section placement and rendering**

Run:
```bash
grep -n "^## " /home/lbihari/cognitive-castle/README.md
```

Expected: section order is `Quickstart` → `Going further: better recall with bge-m3` → `How it works` → (rest unchanged).

- [ ] **Step 3: Confirm both flag examples + config snippet are present**

Run:
```bash
grep -E "embedder_model|embedder_dim|--embedder|--embedder-dim" /home/lbihari/cognitive-castle/README.md
```

Expected: the YAML snippet (`embedder_model: BAAI/bge-m3` + `embedder_dim: 1024`), the one-shot CLI variant, and the help text references all appear.

- [ ] **Step 4: Confirm the footgun warning text appears verbatim**

Run:
```bash
grep -E "Forget-to-reindex|query dim\(1024\) doesn't match" /home/lbihari/cognitive-castle/README.md
```

Expected: the warning subsection heading and the verbatim error-message example both appear.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs(readme): add 'Going further: better recall with bge-m3' section

Lands immediately after Quickstart with:
- Both castle.yaml keys (embedder_model AND embedder_dim — preventing the
  silent 384-vs-1024 broken-palace bug we caught in spec review)
- Two-step + one-shot migration commands
- Known model→dim pairs table
- Explicit forget-to-reindex footgun warning with verbatim LanceDB error

No default change — current users with no config edits are unaffected.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Reproducible smoke test (acceptance #9)

This isn't a code task — it's the manual smoke documented in Acceptance #9 of the spec. Run it on the implementer's machine to verify end-to-end behavior, then capture the result for the PR description.

**Files:** none (filesystem only)

- [ ] **Step 1: Prepare the smoke environment**

Run:
```bash
rm -rf /tmp/castle-smoke
mkdir -p /tmp/castle-smoke/{palace,src}
echo "Hello world from bge-m3 smoke test. Ahoj jak se mas." > /tmp/castle-smoke/src/note.md
```

Expected: no errors. `ls /tmp/castle-smoke/src/` shows `note.md`.

- [ ] **Step 2: Run the one-shot reindex**

Run:
```bash
castle reindex \
  --palace /tmp/castle-smoke/palace \
  --sources /tmp/castle-smoke/src \
  --embedder BAAI/bge-m3 \
  --embedder-dim 1024 \
  --yes
```

Expected: completes without errors. Output mentions "Reindex complete." (or similar — read the actual print() output at `cli.py:669-672`). Total time depends on whether the bge-m3 model is cached locally: ~10s warm, several minutes cold.

- [ ] **Step 3: Verify the new palace has 1024-dim vectors**

Run:
```bash
python -c "
import lancedb
db = lancedb.connect('/tmp/castle-smoke/palace')
print('tables:', db.table_names())
for name in db.table_names():
    t = db.open_table(name)
    print(f'  {name}: {t.count_rows()} rows, schema:')
    for field in t.schema:
        print(f'    {field.name}: {field.type}')
"
```

Expected: at least one table with a `vector` field typed `fixed_size_list<...>[1024]` (the exact display string may vary slightly between PyArrow versions, but the dim must be `1024`).

- [ ] **Step 4: Verify negative case (paired-flag enforcement)**

Run:
```bash
castle reindex \
  --palace /tmp/castle-smoke/palace2 \
  --sources /tmp/castle-smoke/src \
  --embedder BAAI/bge-m3 \
  --yes
echo "exit code: $?"
```

Expected: stderr contains `"--embedder and --embedder-dim must be passed together"`. Exit code is `2`. No palace was created at `/tmp/castle-smoke/palace2` (validation fires before filesystem work).

- [ ] **Step 5: Clean up**

Run:
```bash
rm -rf /tmp/castle-smoke
```

No commit (no code changes). Capture the smoke results for the PR description.

---

## Task 9: Final acceptance verification

Walk through all 10 acceptance criteria from the spec.

**Files:** none (verification only)

- [ ] **Step 1: Acceptance #1 — slow regression test passes**

Run:
```bash
pytest tests/test_embedding.py::test_bge_m3_loads_and_embeds_at_1024_dim -v -m slow
```

Expected: 1 passed.

- [ ] **Step 2: Acceptance #2 — default test suite passes (no regression)**

Run:
```bash
pytest tests/ -v --ignore=tests/benchmarks
```

Expected: at least the same number of passing tests as before the PR + 2 new tests (the pair-validation tests). Pre-existing failures are documented in project memory as CI-UNSTABLE and acceptable.

- [ ] **Step 3: Acceptance #3 — pair-validation tests pass**

Run:
```bash
pytest tests/test_cli.py::test_reindex_rejects_unpaired_embedder_flags tests/test_cli.py::test_reindex_rejects_unpaired_dim_flag -v
```

Expected: 2 passed.

- [ ] **Step 4: Acceptance #4 — `castle reindex --help` shows new flags**

Run:
```bash
castle reindex --help
```

Expected output includes lines for `--embedder MODEL_NAME` and `--embedder-dim N`, each with the help text added in Task 3.

- [ ] **Step 5: Acceptance #5 + #6 — README content**

Run:
```bash
grep -A1 "^## Going further" /home/lbihari/cognitive-castle/README.md | head -5
grep -E "embedder_model: BAAI/bge-m3|embedder_dim: 1024" /home/lbihari/cognitive-castle/README.md
grep -E "Forget-to-reindex|query dim\(1024\) doesn't match" /home/lbihari/cognitive-castle/README.md
grep -E "BAAI/bge-large-en-v1.5" /home/lbihari/cognitive-castle/README.md
```

Expected: all four greps return matches (section heading, config snippet, footgun warning, third row of the known-pairs table).

- [ ] **Step 6: Acceptance #7 — CLAUDE.md updated**

Run:
```bash
grep -n "paraphrase-multilingual-MiniLM" /home/lbihari/cognitive-castle/CLAUDE.md
```

Expected: both matching lines (87 and 179) now also reference `bge-m3` alongside MiniLM. No remaining lines claim MiniLM is the only embedder.

- [ ] **Step 7: Acceptance #8 — lint clean**

Run:
```bash
ruff check . && ruff format --check .
```

Expected: no errors.

- [ ] **Step 8: Acceptance #9 — smoke recipe**

Already verified in Task 8. Confirm by re-reading Task 8 results.

- [ ] **Step 9: Acceptance #10 — default behavior unchanged**

Run:
```bash
unset CASTLE_EMBEDDER_MODEL CASTLE_EMBEDDER_DIM
castle reindex --help | grep -E "embedder|dim"
```

Then run a quick reindex on a fresh tmp palace WITHOUT the new flags:
```bash
rm -rf /tmp/castle-default-check
mkdir -p /tmp/castle-default-check/{palace,src}
echo "default check" > /tmp/castle-default-check/src/note.md
castle reindex \
  --palace /tmp/castle-default-check/palace \
  --sources /tmp/castle-default-check/src \
  --yes
python -c "
import lancedb
db = lancedb.connect('/tmp/castle-default-check/palace')
for name in db.table_names():
    t = db.open_table(name)
    for field in t.schema:
        if field.name == 'vector':
            print(f'{name}.vector: {field.type}')
"
rm -rf /tmp/castle-default-check
```

Expected: vector field is `fixed_size_list<...>[384]` (the MiniLM default dim — proving no behavior change for users who didn't opt in).

- [ ] **Step 10: Push branch + open PR**

Run:
```bash
git push -u origin feat/bge-m3-unblock
gh pr create \
  --title "feat: enable bge-m3 embedder via paired CLI flags + docs" \
  --body "$(cat <<'EOF'
## Summary

PR #1 of the SOTA-retrieval umbrella. Makes `BAAI/bge-m3` a documented, tested, opt-in embedder for Cognitive Castle.

- Adds paired `--embedder MODEL_NAME` and `--embedder-dim N` flags to `castle reindex` (must be passed together; argparse-enforced via `sys.exit(2)`)
- New "Going further: better recall with bge-m3" section in README with two-step + one-shot migration commands, known model→dim pairs table, and an explicit forget-to-reindex footgun warning
- New `@pytest.mark.slow` regression test that bge-m3 still loads + embeds at 1024-dim (catches future regressions of the SDP-disable workaround)
- Two new argparse pair-validation tests in `tests/test_cli.py`
- CLAUDE.md updated to note bge-m3 as a supported alternative
- **No default change** — users with no config edits get exactly the same MiniLM-384 experience as before

Spec: `docs/superpowers/specs/2026-05-12-bge-m3-unblock-design.md` (commit `a4876b60`).

## Pre-existing reindex behavior (informational)

`castle reindex` rebuilds LanceDB vectors + closets but does NOT rebuild the knowledge graph or entity registry — they reset on reindex. This is pre-existing behavior, not introduced by this PR. Users with rich KG / entity-registry state should be aware before migrating.

## Follow-up (out of scope)

`EmbedderIdentityMismatchError` is defined in `backends/base.py:53` and referenced in `config.py:347-364`, but `lancedb_backend.py` has zero call sites that raise it. Wiring this up (~30 LOC) would convert the cryptic LanceDB dim-mismatch error into a friendly "please reindex" message. Tracked as a separate follow-up PR.

## Test plan

- [x] `pytest tests/test_embedding.py::test_bge_m3_loads_and_embeds_at_1024_dim -v -m slow` passes
- [x] `pytest tests/test_cli.py -v` passes (incl. 2 new pair-validation tests)
- [x] `pytest tests/ -v --ignore=tests/benchmarks` — no new regressions
- [x] `ruff check .` and `ruff format --check .` clean
- [x] `castle reindex --help` shows both new flags
- [x] Smoke: one-shot reindex with `--embedder BAAI/bge-m3 --embedder-dim 1024` produces a palace with 1024-dim vectors
- [x] Smoke: unpaired flag (just `--embedder`) exits with code 2 and clear stderr message
- [x] Smoke: no-flag reindex still produces a 384-dim palace (default unchanged)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR opens at `https://github.com/Testimonial/cognitive-castle/pull/<N>`. Report the URL.

---

## Self-Review

**Spec coverage check:** every acceptance criterion in the spec maps to a verification step in Task 9:

| Spec acceptance | Verified by |
|---|---|
| #1 slow test | Task 9 Step 1 |
| #2 default suite | Task 9 Step 2 |
| #3 pair-validation test | Task 9 Step 3 |
| #4 `--help` shows flags | Task 9 Step 4 |
| #5 README content | Task 9 Step 5 |
| #6 model→dim pairs table | Task 9 Step 5 (4th grep) |
| #7 CLAUDE.md | Task 9 Step 6 |
| #8 ruff clean | Task 9 Step 7 |
| #9 smoke recipe | Task 8 + Task 9 Step 8 |
| #10 default unchanged | Task 9 Step 9 |

**Type consistency check:**
- Pair-flag args are `args.embedder` (str | None) and `args.embedder_dim` (int | None) throughout — Tasks 2, 3, 4 all use these exact names.
- Env vars are `CASTLE_EMBEDDER_MODEL` and `CASTLE_EMBEDDER_DIM` consistently — match `config.py:313, :330` per the spec.
- Error message is the exact string `"--embedder and --embedder-dim must be passed together"` in both Task 2 (test) and Task 4 (implementation).
- Exit code is `2` consistently.
- `sys.exit(2)` (not `return 2`) — matches the spec's revision-3 fix.

**Placeholder scan:** no TBDs, no "implement later", no "add validation" — every code-modification step shows the exact code to write or the exact text to replace. Every command shows exact arguments. Expected outputs are stated for every test/lint/grep step.

**Inconsistencies fixed inline during review:** none surfaced — the plan reads consistently end-to-end.
