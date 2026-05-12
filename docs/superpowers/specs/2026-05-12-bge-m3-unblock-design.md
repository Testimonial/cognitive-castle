# bge-m3 Unblock + Migration — Design Spec

**Date:** 2026-05-12
**Status:** Approved, ready for implementation plan
**Umbrella:** SOTA retrieval upgrade — PR #1 of 4 (see Sequencing below)

---

## Background

Castle's retrieval ceiling is set primarily by its dense embedder. The current
default, `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, is a
384-dim multilingual model that benchmarks well below SOTA (the model is from
2019). `BAAI/bge-m3` is a 1024-dim multilingual model that consistently
outperforms MiniLM on MTEB retrieval tasks and is the largest single available
R@5 lift for Castle.

bge-m3 was attempted during the earlier SOTA retrieval upgrade cycle and was
deferred when its first use triggered a >3-minute CUDA flash-attention JIT
compilation hang on the user's hardware. A workaround landed in
`embedding.py:92-100` that disables `flash_sdp` and `mem_efficient_sdp` after
model load, forcing PyTorch to use the math SDP backend (no JIT, <1ms cost).

**Live verification (2026-05-12, RTX 3080, torch 2.11 + CUDA 13):**

| Metric | Value |
|---|---|
| Load time | 7.92 s |
| VRAM used | 2.27 GB |
| First encode (3 strings) | 0.16 s |
| Output dim | 1024 ✓ |
| L2-normalized | ✓ |

The workaround holds. bge-m3 is unblocked. This spec is therefore a
**migration spec**, not a hang-fix spec — the code path already works; what's
missing is documentation, a regression test, and a small UX flag.

## Umbrella context

This is the first of four sub-projects under the SOTA-retrieval umbrella. Each
ships independently with its own spec cycle:

| # | Sub-project | Scope | Status |
|---|---|---|---|
| 1 | bge-m3 unblock + migration | THIS SPEC | In design |
| 2 | mxbai-rerank-large-v2 swap | Reranker upgrade — drop-in model swap | Future |
| 3 | LLM-as-judge Stage 4 (opt-in) | Optional `--rerank-via-llm` flag using local gemma3:e4b | Future |
| 4 | Fusion rules engine | Declarative rules DSL in `castle.yaml` for query-aware fusion weighting | Future |

Each subsequent sub-project will get its own spec when its turn comes — we do
not lock design decisions for PRs #2-#4 here.

## Goal

Make `BAAI/bge-m3` a documented, tested, recommended embedder option for Castle.
No default change. Users opt in by editing `castle.yaml` (or passing a new
CLI flag) and running `castle reindex`.

## Non-goals

- Changing the default embedder — that is a separate "cutover" decision worth
  its own PR with benchmark evidence.
- Running R@5 comparisons against MiniLM as a merge gate — benchmarks are
  encouraged in the PR description as informational, not a blocker.
- Auto-detecting embedder/dim mismatch on palace open and offering reindex —
  nice-to-have, not in scope.
- Touching the reranker, fusion, or LLM-as-judge — those are PRs #2-#4.

## Architecture

Zero new modules. The infrastructure all exists:

- `embedding._get_model()` (in `cognitive_castle/embedding.py`) already accepts
  arbitrary HuggingFace model names via `cfg.embedder_model`. Tested at
  `tests/test_embedding.py:26-32`.
- The SDP-disable workaround at `embedding.py:92-100` resolves the original
  JIT hang. Live verification confirms this on torch 2.11.
- `castle reindex` (`cli.py:629`) already handles palace rebuild end-to-end:
  moves the old palace to `.legacy/`, creates a fresh one, mines sources into
  it. Documented at `cli.py:702`.
- LanceDB tables are created at the embedder's native dim, so reindex always
  produces a clean dim-consistent palace. Mixing dims is structurally
  impossible.

This PR adds **one** small convenience and **two** documentation surfaces.

## Components (file-level changes)

| File | Change | Approx LOC |
|---|---|---|
| `README.md` | Add "Going further: better recall with bge-m3" section — exact config snippet, reindex command, hardware requirements (≈2.3 GB VRAM, or CPU fallback). Positioned as opt-in for multilingual users and users who want higher recall. | +30, -0 |
| `CLAUDE.md` | Update the embedder reference (currently names `paraphrase-multilingual-MiniLM-L12-v2` as the default model) to note that bge-m3 is a supported alternative. | +3, -1 |
| `cognitive_castle/cli.py` | Add `--embedder MODEL_NAME` flag to `castle reindex`. When passed, it sets the embedder model for THIS reindex run only (no config-file write). Avoids users needing to edit `castle.yaml` for a one-shot migration. | +15 |
| `tests/test_embedding_bge_m3.py` (new) | Slow regression test: load bge-m3 via `_get_model`, encode 3 multilingual strings, assert 1024-dim L2-normalized output. Marked `@pytest.mark.slow` so it does not run by default (model download is ~2 GB; the existing pytest config at `pyproject.toml:77` excludes slow tests by default). | +40 |

Total: ~90 LOC, 4 files, no new modules.

## Data flow

### User-facing migration journey (documented in README)

```
1. Edit ~/.castle.yaml (or palace-local castle.yaml):

     embedder_model: BAAI/bge-m3

2. Run reindex:

     castle reindex --palace ~/.castle/palace --sources ~/projects --yes

   Or, for one-shot migration without editing config:

     castle reindex --palace ~/.castle/palace --sources ~/projects \
       --embedder BAAI/bge-m3 --yes

3. Verify (run a few searches you know the answer to).

4. Delete the legacy backup when satisfied:

     rm -rf ~/.castle/palace.legacy
```

### Internal data flow (no changes — verified working)

```
castle reindex
  → cmd_reindex (cli.py:629)
  → if --embedder passed: override cfg.embedder_model for this process
  → moves <palace>/ to <palace>.legacy/
  → creates fresh <palace>/
  → miner.mine(project_dir, palace_path) for each source
      → backends/lancedb_backend.py creates LanceDB table sized at embed_dim
      → embedding._get_model() reads cfg.embedder_model ("BAAI/bge-m3")
      → SDP workaround at embedding.py:92-100 prevents JIT hang
      → embeddings written at 1024-dim
```

### Implementation note for the `--embedder` flag

The cleanest implementation is to set the model in the active config object
before calling `miner.mine`. The miner reads embedder config through the same
path used by interactive search, so a single override at the top of
`cmd_reindex` propagates correctly.

```python
# Sketch — final implementation in plan, not here:
if args.embedder:
    # Override in-process; do NOT persist to castle.yaml
    os.environ["CASTLE_EMBEDDER_MODEL"] = args.embedder
```

(Or whatever override mechanism CognitiveCastleConfig supports — the plan will
nail the exact wiring after reading config.py.)

## Error handling

**No new error surface introduced by this PR.** Existing protections cover all
foreseeable failure modes:

| Failure | Existing handler | Path |
|---|---|---|
| CUDA OOM on model load | CPU fallback with stderr warning (PR #18) | `embedding.py:66-82` |
| Model download fails | `SentenceTransformer` raises a clear HF error; propagates to reindex stderr | sentence-transformers internal |
| First-encode JIT hang | SDP-disable workaround | `embedding.py:92-100` |
| Dim mismatch on existing palace | Structurally prevented — reindex always creates fresh table | by construction |

**Decision: no VRAM pre-flight check.** The existing CUDA OOM → CPU fallback
already produces a clear stderr message. Pre-flight checks are noisy, fragile
(VRAM is shared across processes), and YAGNI. If users hit slow CPU encoding
without realizing why, we can revisit in a future PR.

## Testing

### New test (1)

`tests/test_embedding_bge_m3.py` — slow regression test:

```python
import pytest
from unittest.mock import MagicMock
import cognitive_castle.embedding as emb


@pytest.mark.slow
def test_bge_m3_loads_and_embeds_at_1024_dim():
    """Regression: bge-m3 must load + first-encode without hanging.

    The SDP-disable workaround in embedding._get_model is what makes this
    possible. If a future torch upgrade breaks the workaround, this test
    catches it before users hit a 3-minute hang in production reindex.
    """
    cfg = MagicMock()
    cfg.embedder_model = "BAAI/bge-m3"
    model = emb._get_model(device="auto", cfg=cfg)
    vecs = model.encode(
        ["hello world", "ahoj jak se mas", "cognitive castle"],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    assert vecs.shape == (3, 1024)
    assert abs(float((vecs[0] ** 2).sum()) ** 0.5 - 1.0) < 1e-4
```

The `@pytest.mark.slow` marker is already registered at `pyproject.toml:78-82`
and excluded from default runs (`addopts = "-m 'not benchmark and not slow and not stress'"`),
so this test runs only on demand via `pytest -m slow`.

### Default suite

No existing tests change. All current tests pass unchanged.

## Acceptance criteria

The PR is mergeable when ALL of these hold:

1. `pytest tests/test_embedding_bge_m3.py -v -m slow` passes (bge-m3 loads,
   embeds, returns 1024-dim L2-normalized output).
2. Default test suite passes:
   `pytest tests/ -v --ignore=tests/benchmarks`.
3. `castle reindex --help` shows the new `--embedder` flag with clear help
   text describing what model names are accepted.
4. README has a "Going further: better recall with bge-m3" section containing:
   - The `castle.yaml` config snippet
   - Both the two-step migration command and the one-shot `--embedder` variant
   - Hardware note (≈2.3 GB VRAM with GPU; falls back to CPU)
5. CLAUDE.md no longer claims `paraphrase-multilingual-MiniLM-L12-v2` is the
   only supported embedder — names bge-m3 as an alternative.
6. `ruff check .` and `ruff format --check .` both pass clean.
7. Manual smoke documented in PR description:
   `castle reindex --embedder BAAI/bge-m3 --palace /tmp/test --sources /tmp/fake --yes`
   produces a fresh palace with 1024-dim drawer vectors.
8. Default behavior unchanged: users with no config edits and no CLI flag
   get exactly the same MiniLM-384 experience as before the PR.

## Out of scope (explicit non-goals revisited)

- Default-embedder change (separate cutover PR)
- R@5 benchmark vs MiniLM as a merge gate (informational only)
- Reranker, fusion, LLM-judge upgrades (PRs #2-#4 in the umbrella)
- Auto dim-mismatch detection on palace open
- VRAM pre-flight check

## Spec self-review

1. **Placeholders:** None. The `os.environ` sketch in the data-flow section is
   labeled as a sketch — the implementation plan will read `config.py` to
   nail the exact override mechanism.
2. **Internal consistency:** Architecture, components, data flow, and
   acceptance criteria all reference the same 4 files and the same `--embedder`
   flag semantics. CLAUDE.md note matches Section 2.
3. **Scope:** Single sub-project (bge-m3 unblock + migration). Other three
   sub-projects in the umbrella are explicitly deferred to their own spec
   cycles. Scope is correctly atomic.
4. **Ambiguity:** The `--embedder` flag is process-scoped (does not persist to
   `castle.yaml`) — that's stated explicitly in Components and Data Flow. No
   other dual-interpretable requirements.
