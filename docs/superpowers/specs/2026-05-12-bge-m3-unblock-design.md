# bge-m3 Unblock + Migration — Design Spec

**Date:** 2026-05-12
**Status:** Revised after review (2026-05-12) — ready for implementation plan
**Umbrella:** SOTA retrieval upgrade — PR #1 of 4 (see Sequencing below)

## Revision history

- **2026-05-12 (initial):** First draft, approved section-by-section.
- **2026-05-12 (post-review #1):** Three issues found:
  1. Migration snippet missed `embedder_dim` — UX bug (reindex would fail with cryptic LanceDB cast errors rather than a friendly "set both" message).
  2. Mislabeled "auto-detect dim mismatch" as non-existent when it's actually a defined-but-unwired stub (`EmbedderIdentityMismatchError`).
  3. Reindex rebuilds drawers + closets but not KG / entity registry — worth being explicit.
- **2026-05-12 (post-review #2):** Two contradictions surfaced + footgun severity verified empirically:
  4. Architecture "Mixing dims is structurally impossible" claim contradicted the Critical Migration Note. Reworded with the verified empirical behavior (LanceDB enforces dim at both write and query time with clear errors, but the error messages are cryptic).
  5. Error-handling table had the same wrong claim. Reworded.
  6. Test 2 implicitly required `cmd_reindex` to return an exit code — now stated explicitly as a signature change.
  7. Footgun severity verified: LanceDB raises clear errors on dim mismatch at both query and write time. The actual problem is error-message UX (cryptic "Cast error: Cannot cast to FixedSizeList(384)") not silent data corruption. Wording softened across the spec.

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
No default change. Users opt in by editing `castle.yaml` (or passing new CLI
flags) and running `castle reindex`.

## Non-goals

- Changing the default embedder — that is a separate "cutover" decision worth
  its own PR with benchmark evidence.
- Running R@5 comparisons against MiniLM as a merge gate — benchmarks are
  encouraged in the PR description as informational, not a blocker.
- Touching the reranker, fusion, or LLM-as-judge — those are PRs #2-#4.
- **Wiring up `EmbedderIdentityMismatchError` enforcement in the LanceDB
  backend.** This safety mechanism is defined in `backends/base.py:53` and
  documented in `config.py:347-364` as raising on stale palaces, but
  `lancedb_backend.py` does not currently enforce it (zero call sites). Wiring
  it up is a separate ~30 LOC PR worth doing soon — but expanding this PR's
  scope to include it would mix "documentation + migration enablement" with
  "backend safety net." This spec calls the gap out explicitly in the README
  ("forget-to-reindex footgun") and acceptance criteria so the migration story
  is honest, then leaves the wiring as a follow-up.

## Architecture

Zero new modules. The infrastructure all exists:

- `embedding._get_model()` (in `cognitive_castle/embedding.py`) already accepts
  arbitrary HuggingFace model names via `cfg.embedder_model`. Tested at
  `tests/test_embedding.py:26-32`.
- The SDP-disable workaround at `embedding.py:92-100` resolves the original
  JIT hang. Live verification confirms this on torch 2.11.
- `castle reindex` (`cli.py:629-672`) already handles palace rebuild end-to-end:
  moves the old palace to `.legacy/`, creates a fresh one, mines sources into
  it.
- LanceDB tables are created at `cfg.embedder_dim`, which is a SEPARATE config
  knob from `cfg.embedder_model`. LanceDB enforces dim at both write and query
  time via PyArrow `FixedSizeList(dim)` (verified empirically — see
  Migration Note below). The implication: `embedder_model` and `embedder_dim`
  MUST be set consistently or the system raises clear LanceDB errors at the
  first operation. There is no silent corruption, but the error messages are
  cryptic and don't point users at the config fix.

This PR adds **one** small convenience (paired CLI flags) and **two**
documentation surfaces (README migration section + CLAUDE.md update).

## Components (file-level changes)

| File | Change | Approx LOC |
|---|---|---|
| `README.md` | Add **"Going further: better recall with bge-m3"** subsection immediately after the existing Quickstart section (so it appears right after install/first-run, where users will look). Includes: config snippet (BOTH `embedder_model` AND `embedder_dim` — see Critical migration note below), the two-step + one-shot migration commands, hardware requirements (≈2.3 GB VRAM with GPU, CPU fallback supported but slow), and an explicit ⚠️ note that editing config without running reindex will produce wrong results (the identity-check stub is not yet wired up). | +35, -0 |
| `CLAUDE.md` | Update the embedder reference in the retrieval-pipeline diagram (currently names `paraphrase-multilingual-MiniLM-L12-v2` as the model) to note that bge-m3 is a supported alternative via config. | +3, -1 |
| `cognitive_castle/cli.py` | Add `--embedder MODEL_NAME` AND `--embedder-dim N` flags to `castle reindex`. Both must be passed together when used (the argparse validation enforces this); either both or neither — passing only one is a usage error. When passed, they set `CASTLE_EMBEDDER_MODEL` and `CASTLE_EMBEDDER_DIM` in the process env before calling `miner.mine`. No config-file write. Help text on each flag points users at the README for known model→dim pairs. | +25 |
| `tests/test_embedding.py` (existing) | Extend with one new `@pytest.mark.slow` test (`test_bge_m3_loads_and_embeds_at_1024_dim`) — does not create a new test file (convention in this repo is one test file per module). | +30 |

Total: ~95 LOC, 4 files, no new modules.

### Critical migration note (the bug the review caught)

`config.py` exposes **two separate** retrieval-affecting knobs:

| Property | Default | Env var |
|---|---|---|
| `embedder_model` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | `CASTLE_EMBEDDER_MODEL` |
| `embedder_dim` | `384` | `CASTLE_EMBEDDER_DIM` |

Switching to bge-m3 requires setting **both**. Verified empirical behavior
when only `embedder_model` is set:

- Reindex starts, miner generates 1024-dim embeddings, LanceDB raises
  `ValueError: Cast error: Cannot cast to FixedSizeList(384): value at index 0
  has length 1024` at the first write.
- The palace at `.legacy/` is preserved (move happens first).
- No silent corruption, but the error message doesn't tell the user "set
  embedder_dim too."

The README must show both keys in every migration snippet, and the
`--embedder` / `--embedder-dim` CLI flags must be passed together (argparse-
validated in `cmd_reindex`). The intent is to make the misconfiguration
impossible at the entry points users actually touch, since the underlying
LanceDB error is cryptic.

### Known model→dim pairs documented in README

| Short label | `embedder_model` | `embedder_dim` |
|---|---|---|
| Default (current) | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 384 |
| bge-m3 (recommended) | `BAAI/bge-m3` | 1024 |
| bge-large-en-v1.5 | `BAAI/bge-large-en-v1.5` | 1024 |

We don't ship a built-in lookup table in code (YAGNI — README documents the
common cases; the CLI requires explicit `--embedder-dim` so user always knows
what they're setting).

## Data flow

### User-facing migration journey (documented in README)

```
1. Edit ~/.castle.yaml (or palace-local castle.yaml) — set BOTH keys:

     embedder_model: BAAI/bge-m3
     embedder_dim: 1024

2. Run reindex:

     castle reindex --palace ~/.castle/palace --sources ~/projects --yes

   Or, for one-shot migration without editing config (both flags required):

     castle reindex --palace ~/.castle/palace --sources ~/projects \
       --embedder BAAI/bge-m3 --embedder-dim 1024 --yes

3. Verify (run a few searches you know the answer to).

4. Delete the legacy backup when satisfied:

     rm -rf ~/.castle/palace.legacy
```

**⚠️ Footgun warning (called out in README):** Editing `castle.yaml` without
running `castle reindex` will cause the next search to fail with a cryptic
LanceDB error like `query dim(1024) doesn't match the column vector vector
dim(384)`. There is no silent corruption — the system errors loudly — but the
error doesn't tell users they need to reindex. Always run `castle reindex`
after changing embedder config. A friendlier error pointing users at the fix
is tracked as the follow-up `EmbedderIdentityMismatchError` wiring PR.

### What reindex rebuilds and what it doesn't

| Palace component | Rebuilt by `castle reindex`? |
|---|---|
| LanceDB drawer table (vectors) | ✅ Yes, at new dim |
| LanceDB closets table | ✅ Yes, via `miner.mine` |
| Tantivy FTS index | ✅ Yes, via LanceDB |
| Knowledge graph (SQLite) | ❌ No — the old palace moves to `.legacy/`, the new palace starts with empty KG |
| Entity registry | ❌ No — same as KG, starts empty |
| Diary entries | ❌ Not rebuilt from sources; only present if explicitly re-ingested via `castle diary` |

This is **pre-existing reindex behavior**, not a regression introduced by this
PR. Users with rich KG / entity-registry history should be aware that
`castle reindex` is a vector-layer rebuild, not a full palace rebuild. The
spec calls this out so the migration story is honest; addressing it
(reindex-rebuilds-KG) is a separate concern outside this umbrella.

### Internal data flow (no changes — verified working)

```
castle reindex --embedder BAAI/bge-m3 --embedder-dim 1024 [...]
  → cmd_reindex (cli.py:629)
  → argparse validates --embedder and --embedder-dim came as a pair
  → sets os.environ["CASTLE_EMBEDDER_MODEL"] and os.environ["CASTLE_EMBEDDER_DIM"]
    (process-scoped; CognitiveCastleConfig reads env first per config.py:313 + :330)
  → moves <palace>/ to <palace>.legacy/
  → creates fresh <palace>/
  → miner.mine(project_dir, palace_path) for each source
      → backends/lancedb_backend.py creates LanceDB table sized at embedder_dim (1024)
      → embedding._get_model() reads cfg.embedder_model ("BAAI/bge-m3")
      → SDP workaround at embedding.py:92-100 prevents JIT hang
      → 1024-dim embeddings written
```

### Implementation note for the flags (now concrete)

`CASTLE_EMBEDDER_MODEL` and `CASTLE_EMBEDDER_DIM` are already wired through
`CognitiveCastleConfig` (`config.py:313` and `config.py:330`). The CLI flag
implementation is purely a process-env override at the top of `cmd_reindex`:

```python
# Final implementation pattern (plan will use exactly this):
if (args.embedder is None) != (args.embedder_dim is None):
    print("--embedder and --embedder-dim must be passed together", file=sys.stderr)
    return 2
if args.embedder is not None:
    os.environ["CASTLE_EMBEDDER_MODEL"] = args.embedder
    os.environ["CASTLE_EMBEDDER_DIM"] = str(args.embedder_dim)
```

No config-file write, no persistence — the next process reads from
`castle.yaml` as usual.

## Error handling

**No new error surface introduced by this PR.** Existing protections cover all
foreseeable failure modes:

| Failure | Existing handler | Path |
|---|---|---|
| CUDA OOM on model load | CPU fallback with stderr warning (PR #18) | `embedding.py:66-82` |
| Model download fails | `SentenceTransformer` raises a clear HF error; propagates to reindex stderr | sentence-transformers internal |
| First-encode JIT hang | SDP-disable workaround | `embedding.py:92-100` |
| Dim mismatch on write (model/dim config out of sync) | LanceDB raises `ValueError: Cast error: Cannot cast to FixedSizeList(N)` at the first write — no silent corruption, but the error is cryptic. Paired CLI flags prevent this at the entry point users touch. | `lancedb_backend.py` via PyArrow |
| Dim mismatch on query (config changed without reindex) | LanceDB raises `RuntimeError: query dim(N) doesn't match the column vector vector dim(M)`. Search fails loudly. | `lancedb_backend.py` via Lance |

**Decision: no VRAM pre-flight check.** The existing CUDA OOM → CPU fallback
already produces a clear stderr message. Pre-flight checks are noisy, fragile
(VRAM is shared across processes), and YAGNI. If users hit slow CPU encoding
without realizing why, we can revisit in a future PR.

## Testing

### New test (1) — added to existing `tests/test_embedding.py`

The new test extends the existing module file (one test file per module is
the repo convention) rather than creating a new test file:

```python
@pytest.mark.slow
def test_bge_m3_loads_and_embeds_at_1024_dim():
    """Regression: bge-m3 must load + first-encode without hanging.

    The SDP-disable workaround in embedding._get_model is what makes this
    possible. If a future torch upgrade breaks the workaround, this test
    catches it before users hit a 3-minute hang in production reindex.
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
    assert abs(float((vecs[0] ** 2).sum()) ** 0.5 - 1.0) < 1e-4
```

The `@pytest.mark.slow` marker is already registered at `pyproject.toml:78-82`
and excluded from default runs (`addopts = "-m 'not benchmark and not slow and not stress'"`),
so this test runs only on demand via `pytest -m slow`.

### New test (2) — argparse pair validation in `tests/test_cli.py`

Two pieces, both small:

**Implementation note (function signature change):** the current
`cmd_reindex` at `cli.py:629` has implicit `None` returns (`return` with no
value on the legacy-backup-exists path, falls through on success). The
paired-flag validation needs to short-circuit with a usage error code, so
`cmd_reindex` now explicitly returns `int` (0 on success, 2 on usage error).
This is a backward-compatible change for the existing dispatcher at
`cli.py:1181` (Python treats implicit `None` as exit 0).

**Test:** construct an argparse `Namespace` with `embedder="BAAI/bge-m3"` and
`embedder_dim=None` (or the reverse), call `cmd_reindex(ns)` directly,
capture stderr via `capsys`, assert:
- `cmd_reindex(ns)` returns `2`
- stderr contains `"--embedder and --embedder-dim must be passed together"`

No model load, no filesystem touch (palace move is gated by the validation
check) — purely argparse + process-env logic.

### Default suite

No existing tests change. All current tests pass unchanged.

## Acceptance criteria

The PR is mergeable when ALL of these hold:

1. `pytest tests/test_embedding.py::test_bge_m3_loads_and_embeds_at_1024_dim -v -m slow`
   passes (bge-m3 loads, embeds, returns 1024-dim L2-normalized output).
2. Default test suite passes:
   `pytest tests/ -v --ignore=tests/benchmarks`.
3. New argparse pair-validation test in `tests/test_cli.py` passes (asserts
   that passing only one of `--embedder` / `--embedder-dim` is a usage error).
4. `castle reindex --help` shows the new `--embedder MODEL_NAME` and
   `--embedder-dim N` flags with help text noting they must be passed together
   and pointing at the README for known model→dim pairs.
5. README has a **"Going further: better recall with bge-m3"** subsection
   placed immediately after Quickstart, containing:
   - The `castle.yaml` config snippet showing BOTH `embedder_model` AND
     `embedder_dim`
   - Both the two-step migration command and the one-shot
     `--embedder ... --embedder-dim ...` variant
   - Hardware note (≈2.3 GB VRAM with GPU; falls back to CPU)
   - ⚠️ explicit warning that editing config without running reindex will
     produce wrong results until `EmbedderIdentityMismatchError` enforcement
     lands in a follow-up PR
6. README documents the known model→dim pairs table (MiniLM 384, bge-m3 1024,
   bge-large-en-v1.5 1024) so users don't have to look up dim themselves.
7. CLAUDE.md no longer claims `paraphrase-multilingual-MiniLM-L12-v2` is the
   only supported embedder — names bge-m3 as an alternative.
8. `ruff check .` and `ruff format --check .` both pass clean.
9. Reproducible manual smoke (documented in PR description):

   ```
   mkdir -p /tmp/castle-smoke/{palace,src}
   echo "Hello world from bge-m3 smoke test" > /tmp/castle-smoke/src/note.md
   castle reindex \
     --palace /tmp/castle-smoke/palace \
     --sources /tmp/castle-smoke/src \
     --embedder BAAI/bge-m3 \
     --embedder-dim 1024 \
     --yes
   ```

   Verify: new palace at `/tmp/castle-smoke/palace/` contains LanceDB tables
   with 1024-dim vectors. Old palace at `/tmp/castle-smoke/palace.legacy/`
   (empty in this case, just confirms reindex moved correctly).

10. Default behavior unchanged: users with no config edits and no CLI flag
    get exactly the same MiniLM-384 experience as before the PR.

### Pre-existing reindex behavior acknowledged (informational, not a gate)

The PR description should note that `castle reindex` rebuilds the LanceDB
vectors and closets but does not rebuild the knowledge graph or entity
registry. This is pre-existing behavior (see "What reindex rebuilds and
what it doesn't" above), not something this PR introduces or fixes.

## Out of scope (explicit non-goals revisited)

- Default-embedder change (separate cutover PR)
- R@5 benchmark vs MiniLM as a merge gate (informational only)
- Reranker, fusion, LLM-judge upgrades (PRs #2-#4 in the umbrella)
- Auto dim-mismatch detection on palace open
- VRAM pre-flight check

## Spec self-review (post-revision #2, 2026-05-12)

1. **Placeholders:** None. The implementation snippet for `--embedder` /
   `--embedder-dim` is concrete (verified `CASTLE_EMBEDDER_MODEL` and
   `CASTLE_EMBEDDER_DIM` exist at `config.py:313, :330`).
2. **Internal consistency:** Architecture, Components, Data Flow, Critical
   Migration Note, Error Handling table, and Acceptance Criteria now all tell
   the same story: dim mismatch raises clear LanceDB errors, paired CLI flags
   prevent the misconfiguration at the entry point. The earlier
   "structurally impossible" contradictions have been removed.
3. **Scope:** Single sub-project (bge-m3 unblock + migration). The
   `EmbedderIdentityMismatchError` wiring (which would convert cryptic
   LanceDB errors into friendly "please reindex" messages) is explicitly
   carved out as a follow-up PR. The KG / entity-registry rebuild gap is
   acknowledged as pre-existing reindex behavior, not in scope.
4. **Ambiguity:** Paired-flag semantics ("both or neither") stated in
   Components, Critical Migration Note, Data Flow, and Acceptance #3. The
   `--embedder` flag is process-scoped (does not persist to `castle.yaml`).
   `cmd_reindex` signature change to `int` return type is stated explicitly
   in Testing.
5. **Empirical verification baked in:** The footgun severity and dim-mismatch
   behavior are grounded in actual LanceDB test output, not assumed.
6. **Review-#2 findings addressed:**
   - ✅ Architecture's "structurally impossible" claim reworded with verified
     LanceDB behavior.
   - ✅ Error-handling table reworded with the same verified behavior.
   - ✅ Test 2 now states the `cmd_reindex` return-type signature change
     explicitly, with concrete test recipe.
   - ✅ Footgun wording softened to match empirical truth (cryptic error, not
     silent corruption).
   - ✅ `cli.py:702` line reference corrected to `cli.py:629-672`.
