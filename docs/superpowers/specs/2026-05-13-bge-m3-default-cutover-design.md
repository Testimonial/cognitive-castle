# bge-m3 Default Cutover + EmbedderIdentityMismatchError Wiring — Design Spec

**Date:** 2026-05-13
**Status:** Approved, ready for implementation plan
**Scope:** the "cutover PR" deliberately deferred by PR #1 (bge-m3 unblock + migration), plus the safety-net wiring queued by PR #4a's umbrella context

## Background

**Two long-standing concerns get resolved together:**

1. **PR #1 deferred the default cutover.** Spec at `docs/superpowers/specs/2026-05-12-bge-m3-unblock-design.md` listed "Changing the default embedder" as an explicit non-goal: *"that is a separate 'cutover' decision worth its own PR with benchmark evidence."* The current default is `paraphrase-multilingual-MiniLM-L12-v2` (384-dim, 2019-era multilingual MiniLM). bge-m3 (1024-dim, 2024-era multilingual) is well-established as superior on MTEB benchmarks — the library-level evidence already exists. Castle's developer has been running bge-m3 personally since PR #1 smoke-tested it. We don't need new benchmarks; the case is the existing public evidence.

2. **`EmbedderIdentityMismatchError` is a stub.** Defined at `backends/base.py:53`, exported at `backends/__init__.py`, referenced in the `cfg.embedder_identity` property docstring at `config.py:349-352` as the mechanism "to detect stale palaces built with a different embedding configuration." But **zero call sites raise it.** PR #4a explicitly carved this out as a follow-up. Without wiring, the cutover would ship cryptic LanceDB cast errors to anyone on a pre-existing palace:
   ```
   RuntimeError: query dim(1024) doesn't match the column vector vector dim(384)
   ```
   (Verified empirically in PR #1 review.)

This PR does both halves in one cutover: flip the defaults AND make `EmbedderIdentityMismatchError` actually fire so legacy users see a friendly migration prompt instead of a cryptic LanceDB error.

## Umbrella context

This is one of the three follow-ups named in PR #4a's umbrella section:

| Follow-up | Status |
|---|---|
| **bge-m3 default cutover** | **THIS SPEC** |
| PR #2-redux docs-only mxbai opt-in | Future |
| `gemma3:e4b` default-LLM-tag fix | ✅ merged at `730493e0` |

## Goal

Flip 3 config defaults in `cognitive_castle/config.py`:
- `embedder_model`: `"sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"` → `"BAAI/bge-m3"`
- `embedder_dim`: `384` → `1024`
- `embedder_identity`: `"paraphrase-ml-MiniLM-L12-v2"` → `"bge-m3"`

AND wire `EmbedderIdentityMismatchError` at the LanceDB backend layer so existing palaces fail loudly with a friendly migration prompt instead of cryptic dim-mismatch errors.

## Non-goals

- **Backend-agnostic identity storage.** Decision: store identity in a LanceDB-native table (`castle_metadata`). Multi-backend support is theoretical; Castle is LanceDB-only since PR #14 deleted ChromaDB. Backend coupling is acceptable here.
- **Structured `EmbedderIdentityMismatchError.__init__` args.** Decision: keep it as a simple message-only exception (just `Exception`'s inherited `__init__(message)`). Construct the friendly migration-prompt message inline at the raise site in `lancedb_backend.py`. Programmatic introspection of the error (e.g., `exc.stored_identity`) isn't needed by current callers; pre-building is speculative.
- **Auto-migration helper command** (`castle migrate-embedder`). The error message itself contains the exact `castle reindex --embedder ... --embedder-dim ... --yes` command; users copy-paste. Building a wrapper is UX polish for a problem that won't be common (most users will start fresh with the new default).
- **Performance benchmarks (R@5 on user's palace).** MTEB-level evidence already exists; library benchmarks of bge-m3 vs MiniLM are conclusive. Smoke testing during PR #1 verified bge-m3 produces useful embeddings on the user's actual data.
- **Reranker work (PR #2-redux mxbai).** Separate concern, separate spec.

## Architecture

### Half 1: Config flips (small)

`cognitive_castle/config.py` — flip 3 defaults across the existing `embedder_model` / `embedder_dim` / `embedder_identity` properties. Docstrings updated to reflect bge-m3 as the new default. ~15 LOC of edits.

### Half 2: Safety net (LanceDB-native, ~80 LOC)

Two-layer check on `LanceDBBackend.__init__`:

**Layer 1 — Empirical dim check (fast, from PyArrow schema, no I/O):**

If `castle_drawers` table exists in the palace:
```python
import pyarrow as pa
table = db.open_table("castle_drawers")
vector_field = next(f for f in table.schema if f.name == "vector")
stored_dim = vector_field.type.list_size  # FixedSizeList(N).list_size
if stored_dim != cfg.embedder_dim:
    raise EmbedderIdentityMismatchError(_dim_mismatch_message(...))
```

This is essentially free — Arrow schema is in memory once the table is opened.

**Layer 2 — Identity check (string compare from castle_metadata):**

If layer 1 passes AND `castle_metadata` table exists:
```python
table = db.open_table("castle_metadata")
rows = table.search().where("key = 'embedder_identity'").limit(1).to_list()
stored_identity = rows[0]["value"] if rows else None
if stored_identity is not None and stored_identity != cfg.embedder_identity:
    raise EmbedderIdentityMismatchError(_identity_mismatch_message(...))
```

If `castle_metadata` is missing (legacy palace), proceed to grandfather (see below).

**Grandfather logic (legacy palaces with no manifest):**

- If `castle_drawers` exists with matching dim AND `castle_metadata` is missing → silently create `castle_metadata` and write `cfg.embedder_identity`. Palace is now manifest-stamped going forward.
- If dim already mismatched (layer 1 raised), we never reach this branch — user gets the friendly error before grandfathering would be attempted.

**Initial write on fresh palace:**

First `LanceDBBackend.add()` to a brand-new palace creates `castle_drawers`, `castle_closets`, AND `castle_metadata` (with the identity row). This happens transactionally per LanceDB's table-creation semantics.

### `castle_metadata` table schema

```python
import pyarrow as pa
metadata_schema = pa.schema([
    pa.field("key", pa.utf8()),
    pa.field("value", pa.utf8()),
])
# Initial row: {"key": "embedder_identity", "value": cfg.embedder_identity}
```

Extensible — future keys (e.g., `created_at`, `castle_version`) can be added without schema migration.

### Error message format (constructed inline)

For dim mismatch (most common case):
```
This palace at <palace_path> was built with embedder dim <stored_dim>
(likely paraphrase-multilingual-MiniLM-L12-v2 if dim=384, or another
model entirely if dim=768/1024/etc), but current config wants dim
<cfg.embedder_dim> (BAAI/bge-m3 default).

Migrate to the new default by running:

  castle reindex --palace <palace_path> --sources <your-sources> \
    --embedder BAAI/bge-m3 --embedder-dim 1024 --yes

Or keep using the old embedder by setting these env vars:

  export CASTLE_EMBEDDER_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
  export CASTLE_EMBEDDER_DIM=384
  export CASTLE_EMBEDDER_IDENTITY=paraphrase-ml-MiniLM-L12-v2
```

For identity mismatch (same dim, different model):
```
This palace at <palace_path> was built with embedder identity
'<stored_identity>' (dim <stored_dim>), but current config wants
identity '<cfg.embedder_identity>' (same dim). The vectors may share
dimensionality but they're in different semantic spaces — searches
would return wrong results.

Migrate to the new identity by running:

  castle reindex --palace <palace_path> --sources <your-sources> \
    --embedder <cfg.embedder_model> --embedder-dim <cfg.embedder_dim> --yes

Or restore the prior identity:

  export CASTLE_EMBEDDER_MODEL=<the model that produced '<stored_identity>'>
  export CASTLE_EMBEDDER_IDENTITY=<stored_identity>
```

## Components (file-level changes)

| File | Change | LOC |
|---|---|---|
| `cognitive_castle/config.py` | Flip 3 defaults at lines 317, 338+343, 361. Update docstrings (lines 306-307, 325, 354) to name bge-m3 as the new default. | +15, -10 |
| `cognitive_castle/backends/lancedb_backend.py` | Add `_check_embedder_compat(palace_path, cfg)` private method called from `__init__`. Implements: open `castle_drawers` if exists → dim check via PyArrow `FixedSizeList.list_size` → raise on mismatch. Then open `castle_metadata` if exists → identity check → raise on mismatch. Helper `_read_stored_identity() -> Optional[str]`. Helper `_write_identity(s: str)`. Add `castle_metadata` table creation logic to the first-write path. Helpers `_dim_mismatch_message(stored_dim, cfg, palace_path)` and `_identity_mismatch_message(stored_identity, cfg, palace_path)` build the inline error messages. | +80 |
| `cognitive_castle/backends/base.py` | NO CHANGES. `EmbedderIdentityMismatchError` stays as the simple message-only exception. (Per Option 2 scope decision — inline construction at raise sites.) | 0 |
| `README.md` | Rewrite the existing "Going further: better recall with bge-m3" subsection (added by PR #1) as a "Migration from MiniLM (pre-cutover users)" subsection. Show the exact `castle reindex` command + the env-var override path. Update the Quickstart section if it names the embedder explicitly. | +30, -20 |
| `CLAUDE.md` | Update line 87 (file tree comment for `embedding.py`) + line 179 (retrieval pipeline diagram) to name bge-m3 as the default, not the alternative. | +3, -3 |
| `tests/test_config.py` | Update the 3 existing tests asserting MiniLM defaults (`test_embedder_model_default`, `test_embedder_dim_default`, `test_embedder_identity_default` or their actual names) to assert bge-m3 defaults instead. | +5, -5 |
| `tests/test_backends.py` (existing) or `tests/test_lancedb_identity_mismatch.py` (new) | 6 new tests for the wiring (see Testing section). | +120 |

**Total: ~280 LOC across 7 files** (3 are net-additions: backend logic + tests + README rewrite). No new modules.

## Data flow

### Fresh palace — first run after this cutover

```
castle init / castle mine / castle reindex
  → LanceDBBackend(palace_path, cfg).__init__
  → palace_path/lancedb/ does NOT exist → check skipped
  → LanceDBBackend.add(...)
  → create castle_drawers (vector field FixedSizeList(1024))
  → create castle_closets
  → create castle_metadata + insert {"key": "embedder_identity", "value": "bge-m3"}
  → palace stamped, future inits will verify identity
```

### Existing bge-m3 palace (developer's current state — already on bge-m3 via PR #1 smoke testing)

```
castle search "..." (or any backend-open path)
  → LanceDBBackend(palace_path, cfg).__init__
  → castle_drawers exists, vector dim = 1024
  → cfg.embedder_dim = 1024 (new default) → dim check passes
  → castle_metadata does NOT exist (legacy — palace built before this PR)
  → grandfather: write {"key": "embedder_identity", "value": "bge-m3"} to a NEW castle_metadata table
  → backend ready, no error, no user disruption
  → subsequent runs: castle_metadata exists, identity matches → silent pass
```

### Legacy MiniLM palace (hypothetical other user upgrading)

```
castle search "..."
  → LanceDBBackend(palace_path, cfg).__init__
  → castle_drawers exists, vector dim = 384
  → cfg.embedder_dim = 1024 (new default) → MISMATCH
  → raise EmbedderIdentityMismatchError(_dim_mismatch_message(384, cfg, palace_path))
  → user sees the friendly migration prompt
  → either runs `castle reindex --embedder BAAI/bge-m3 --embedder-dim 1024 --yes`
  → OR exports CASTLE_EMBEDDER_MODEL/DIM/IDENTITY to keep MiniLM
```

### Same-dim different-model case (e.g., bge-m3 → bge-large-en-v1.5)

```
User changes castle.yaml: embedder_model: BAAI/bge-large-en-v1.5
                          embedder_dim: 1024  (unchanged)
                          embedder_identity: bge-large-en-v1.5
  → LanceDBBackend(palace_path, cfg).__init__
  → castle_drawers dim = 1024, cfg.embedder_dim = 1024 → dim check passes
  → castle_metadata exists, stored_identity = "bge-m3"
  → cfg.embedder_identity = "bge-large-en-v1.5" → MISMATCH
  → raise EmbedderIdentityMismatchError(_identity_mismatch_message("bge-m3", cfg, palace_path))
  → user sees migration prompt naming the identity strings
```

## Error handling

| Failure | Behavior |
|---|---|
| Fresh palace, no tables yet | `__init__` skips both checks. First `add()` creates all 3 tables atomically. |
| Matching dim + matching identity | No exception. Backend ready. |
| Dim mismatch (PyArrow schema differs from cfg) | Raise `EmbedderIdentityMismatchError(_dim_mismatch_message(...))`. Fires BEFORE identity check (cheaper). |
| Identity mismatch (dim matches, identity differs) | Raise `EmbedderIdentityMismatchError(_identity_mismatch_message(...))`. |
| Legacy palace: `castle_drawers` matches cfg dim, `castle_metadata` missing | Silent grandfather: write the identity row. |
| Legacy palace: `castle_drawers` doesn't match cfg dim, `castle_metadata` missing | Raise dim-mismatch error immediately. NO grandfathering attempted. |
| `castle_metadata` exists but empty / missing `embedder_identity` key | Treat as legacy (grandfather if dim matches, raise otherwise). |
| Read of `castle_metadata` fails (corrupted table, permission, etc.) | Wrap in `try/except`. Log a one-time stderr warning, fall back to grandfather-if-dim-matches behavior. Don't crash. |
| Write of `castle_metadata` fails on grandfather (e.g., read-only filesystem) | Log stderr warning, proceed without manifest (palace functional but unstamped). Next run will retry grandfather. |

## Testing

### 6 new tests in `tests/test_backends.py` (extension) or `tests/test_lancedb_identity_mismatch.py` (new file)

```python
def test_fresh_palace_writes_identity_on_first_add(tmp_path, monkeypatch):
    """Empty palace + first add() creates castle_metadata + writes embedder_identity."""
    # Set CASTLE_EMBEDDER_IDENTITY=bge-m3 (the new default)
    # Build a backend, call add() with a tiny doc
    # Open castle_metadata, query for embedder_identity row
    # Assert stored value == "bge-m3"


def test_matching_palace_proceeds_silently(tmp_path, monkeypatch):
    """Palace with matching dim + matching identity → __init__ does not raise."""
    # Build a palace with bge-m3 defaults via the standard add() path
    # Re-instantiate LanceDBBackend on the same palace
    # Assert no exception


def test_dim_mismatch_raises_with_migration_prompt(tmp_path, monkeypatch):
    """Build a 384-dim palace, then re-open with cfg.embedder_dim=1024 → raises."""
    monkeypatch.setenv("CASTLE_EMBEDDER_DIM", "384")
    monkeypatch.setenv("CASTLE_EMBEDDER_IDENTITY", "paraphrase-ml-MiniLM-L12-v2")
    # Build palace at 384
    monkeypatch.setenv("CASTLE_EMBEDDER_DIM", "1024")
    monkeypatch.setenv("CASTLE_EMBEDDER_IDENTITY", "bge-m3")
    with pytest.raises(EmbedderIdentityMismatchError) as exc:
        LanceDBBackend(palace_path, cfg)
    msg = str(exc.value)
    assert "castle reindex" in msg
    assert "--embedder-dim 1024" in msg
    assert "CASTLE_EMBEDDER_MODEL" in msg  # env-var override path


def test_identity_mismatch_raises_when_dim_matches(tmp_path, monkeypatch):
    """Palace with dim=1024 + identity 'bge-large-en-v1.5', cfg wants 'bge-m3' → raises."""
    # Build palace with identity bge-large-en-v1.5 (same dim 1024 as bge-m3)
    # Re-open with cfg.embedder_identity = bge-m3
    with pytest.raises(EmbedderIdentityMismatchError) as exc:
        LanceDBBackend(palace_path, cfg)
    msg = str(exc.value)
    assert "bge-large-en-v1.5" in msg
    assert "bge-m3" in msg


def test_legacy_palace_grandfathers_when_dim_matches(tmp_path, monkeypatch):
    """Palace with castle_drawers but no castle_metadata → on init, grandfather writes."""
    # Build palace via add(), then DELETE castle_metadata table to simulate legacy
    # Re-instantiate LanceDBBackend
    # Assert no exception
    # Assert castle_metadata now exists with the cfg.embedder_identity row


def test_legacy_palace_raises_when_dim_mismatches(tmp_path, monkeypatch):
    """Legacy palace (no manifest) with dim=384 + cfg.embedder_dim=1024 → raise immediately."""
    # Build 384-dim palace, DELETE castle_metadata
    # Re-open with cfg.embedder_dim=1024
    # Assert raises BEFORE attempting grandfather (no castle_metadata write happens)
```

### Update 3 existing tests in `tests/test_config.py`

The `embedder_model` / `embedder_dim` / `embedder_identity` default-value tests assert the OLD defaults. Update each assertion to the new bge-m3 defaults:
- `embedder_model` → `"BAAI/bge-m3"`
- `embedder_dim` → `1024`
- `embedder_identity` → `"bge-m3"`

### Smoke tests (live verification — for PR description, not automated)

**Smoke #1: Developer's own palace (already bge-m3 via PR #1).** Run `castle search "test"` on the existing palace. Expected: grandfather kicks in (palace dim 1024 matches new cfg 1024), `castle_metadata` table created with `embedder_identity = "bge-m3"`. No error, no user disruption. Subsequent runs silent.

**Smoke #2: Simulated legacy MiniLM palace.** Build a 384-dim palace via env-var overrides:
```bash
CASTLE_EMBEDDER_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
CASTLE_EMBEDDER_DIM=384 \
CASTLE_EMBEDDER_IDENTITY=paraphrase-ml-MiniLM-L12-v2 \
  castle reindex --palace /tmp/legacy-smoke/palace --sources /tmp/legacy-smoke/src --yes
```

Then run plain `castle search` (no env vars set → new bge-m3 defaults active). Expected: `EmbedderIdentityMismatchError` raised with the exact migration prompt visible to user.

**Smoke #3: Env-var override (opt-out path).** Same legacy palace; set the env vars per the error message. `castle search` succeeds. Verifies the opt-out path works.

## Acceptance criteria

1. `pytest tests/test_backends.py -v -k "identity_mismatch"` (or the new test file) — **6 passed**.
2. `pytest tests/test_config.py -v -k "embedder"` — 3 default-value tests pass with the new bge-m3 values.
3. `pytest tests/ --ignore=tests/benchmarks` — no NEW failures vs. develop baseline at `ef544327` (current 18 pre-existing CI-UNSTABLE failures).
4. `ruff check` + `ruff format --check` clean on all 7 touched files.
5. **Smoke #1 (your existing bge-m3 palace):** `castle search "test"` succeeds, `castle_metadata` table gets created with `embedder_identity = "bge-m3"`. Verify via `python -c "import lancedb; db = lancedb.connect('<palace>/lancedb'); print(db.open_table('castle_metadata').to_pandas())"`.
6. **Smoke #2 (legacy MiniLM palace):** `castle search` raises `EmbedderIdentityMismatchError` with the exact `castle reindex --embedder BAAI/bge-m3 --embedder-dim 1024` command in the message + the env-var override path.
7. **Smoke #3 (opt-out via env vars):** with `CASTLE_EMBEDDER_MODEL`/`CASTLE_EMBEDDER_DIM`/`CASTLE_EMBEDDER_IDENTITY` set to MiniLM values, `castle search` on the legacy palace succeeds.
8. `castle init --help` shows the new defaults: `--embedder` defaults documented as `BAAI/bge-m3` (or the corresponding env-var docs), `--embedder-dim 1024`.
9. README's "Going further" subsection no longer reads as "opt into bge-m3 if you want better recall." Replaced by "Migration from MiniLM (pre-cutover users)" with the exact reindex command + opt-out env-var path.
10. CLAUDE.md retrieval pipeline diagram + module-listing comment both name bge-m3 as the default.

## Out of scope (deferred)

- **Backend-agnostic identity storage:** kept LanceDB-native per scope decision.
- **Structured `EmbedderIdentityMismatchError.__init__` args:** simple message-only exception per scope decision.
- **`castle migrate-embedder` auto-helper:** error message contains the exact command; users copy-paste.
- **R@5 benchmarks comparing MiniLM vs bge-m3 on the user's palace:** MTEB-level evidence already exists.
- **mxbai reranker work:** separate PR #2-redux concern.

## Spec self-review (2026-05-13)

1. **Placeholders:** None. Helper function names (`_check_embedder_compat`, `_read_stored_identity`, `_write_identity`, `_dim_mismatch_message`, `_identity_mismatch_message`) are concrete. PyArrow schema introspection code shown verbatim.
2. **Internal consistency:** Architecture, Data Flow, Error Handling, Testing, and Acceptance all reference:
   - 3 config flips at exact `config.py` lines (317, 338+343, 361)
   - Two-layer check on `LanceDBBackend.__init__` (dim from PyArrow schema, identity from `castle_metadata` table)
   - `castle_metadata` schema as `{key: utf8, value: utf8}`
   - Grandfather logic (write identity only if dim matches)
   - Inline error-message construction (Option 2 — no structured exception args)
   - Friendly error message format with both migration command + env-var override
3. **Scope:** Single PR with 2 logically-coupled halves (defaults flip + safety net). Could decompose into 2 PRs but they're tightly coupled — flipping defaults without the safety net would break legacy users; wiring the safety net without flipping defaults would be a no-op for the current default. ~280 LOC fits in one PR.
4. **Ambiguity:** Grandfather logic stated in 3 places (Architecture, Data Flow, Error Handling table). LanceDB-native storage decision stated in Non-goals + Architecture. Option 2 inline-error-construction decision stated in Non-goals + Components row.
5. **Empirical grounding:**
   - `embedder_model` / `embedder_dim` / `embedder_identity` defaults confirmed at `config.py:317, 338, 361` (verified via Read)
   - `EmbedderIdentityMismatchError` confirmed at `backends/base.py:53` + exported in `__init__.py` + zero call sites (verified via grep)
   - `vector` column's FixedSizeList type confirmed in `backends/lancedb_backend.py:80-95` (table schema)
   - PR #1's spec confirms cutover was deferred + dim-mismatch behavior was empirically verified
   - PR #4a's umbrella context confirms the safety-net wiring was queued as a follow-up
