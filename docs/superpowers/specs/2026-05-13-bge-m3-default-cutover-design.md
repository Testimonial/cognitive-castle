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

### Half 1: Config flips + auto-derive identity (small)

`cognitive_castle/config.py` — flip 3 defaults across the existing `embedder_model` / `embedder_dim` / `embedder_identity` properties. Docstrings updated to reflect bge-m3 as the new default.

**Auto-derive identity from model.** The current `embedder_identity` property has a static default string. After this change, the property derives a default from `embedder_model` when CASTLE_EMBEDDER_IDENTITY is not explicitly set (env var or yaml). The derivation rule is "strip org prefix" — take the last path component after the last `/`:
- `BAAI/bge-m3` → `bge-m3`
- `BAAI/bge-large-en-v1.5` → `bge-large-en-v1.5`
- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` → `paraphrase-multilingual-MiniLM-L12-v2`

**Why this closes a coordination trap:** the previous design required users changing `embedder_model` to ALSO change `embedder_identity` (and `embedder_dim`). Forgetting either silently stamps the new palace with the wrong identity. With auto-derive, users only need to change `embedder_model` (+ `embedder_dim` if dimensionality differs) — identity follows automatically.

```python
@property
def embedder_identity(self) -> str:
    """Short identity used to stamp palaces. Defaults to last `/` component of embedder_model."""
    explicit = os.environ.get("CASTLE_EMBEDDER_IDENTITY") or self._yaml.get("embedder_identity")
    if explicit:
        return str(explicit).strip()
    model = self.embedder_model
    return model.rsplit("/", 1)[-1] if "/" in model else model
```

**Legacy MiniLM edge case.** The pre-cutover static default was `"paraphrase-ml-MiniLM-L12-v2"` — a custom abbreviation that doesn't match the model's path component (`"paraphrase-multilingual-MiniLM-L12-v2"`). Legacy MiniLM users running on the env-var-override path must now ALSO set `CASTLE_EMBEDDER_IDENTITY=paraphrase-ml-MiniLM-L12-v2` to match their existing palace stamp. The dim-mismatch error message (which fires FIRST for legacy MiniLM users — dim 384 vs 1024) names this exact identity string in its env-var-override block, so the documentation requirement is one-time and explicit.

Roughly +25 LOC of edits (3 default flips + auto-derive property body + docstring updates).

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
import pyarrow.compute as pc
table = db.open_table("castle_metadata")
arrow_table = table.to_arrow()
mask = pc.equal(arrow_table["key"], "embedder_identity")
matched = arrow_table.filter(mask)
stored_identity = matched["value"][0].as_py() if matched.num_rows > 0 else None
if stored_identity is not None and stored_identity != cfg.embedder_identity:
    raise EmbedderIdentityMismatchError(_identity_mismatch_message(...))
```

Note: `castle_metadata` has no `vector` column (it's a pure key/value table), so LanceDB's `.search()` API doesn't apply. Use `to_arrow()` + `pyarrow.compute` for SQL-style filtering. `to_pandas()` would also work but adds a pandas dependency for what's a 1-row lookup.

If `castle_metadata` is missing (legacy palace), proceed to grandfather (see below).

**Grandfather logic (legacy palaces with no manifest):**

- If `castle_drawers` exists with matching dim AND `castle_metadata` is missing → create `castle_metadata` and write `cfg.embedder_identity`. Palace is now manifest-stamped going forward.
- If dim already mismatched (layer 1 raised), we never reach this branch — user gets the friendly error before grandfathering would be attempted.
- **Race-safe creation:** wrap the `db.create_table("castle_metadata", ...)` call in `try/except`. Two processes (e.g., interactive search + a Stop-hook fire) opening the same legacy palace simultaneously could both attempt the grandfather write; LanceDB will fail the second `create_table` with a duplicate-table error. Catch that case, fall back to `db.open_table("castle_metadata")`, and re-run the identity check against whatever the winning process wrote. The fallback path is the steady-state read-existing-manifest path — no special handling needed beyond catching the duplicate-table exception.

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

For dim mismatch (most common case — legacy MiniLM users):
```
This palace at <palace_path> was built with embedder dim <stored_dim>,
but current config wants dim <cfg.embedder_dim> (BAAI/bge-m3 is the
new default since 2026-05-13).

If <stored_dim> is 384, your palace was built with the pre-cutover
default (sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2).

Migrate to the new default by running:

  castle reindex --palace <palace_path> --sources <your-sources> \
    --embedder BAAI/bge-m3 --embedder-dim 1024 --yes

Or keep using MiniLM by setting these env vars (all three required):

  export CASTLE_EMBEDDER_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
  export CASTLE_EMBEDDER_DIM=384
  export CASTLE_EMBEDDER_IDENTITY=paraphrase-ml-MiniLM-L12-v2
```

The `CASTLE_EMBEDDER_IDENTITY=paraphrase-ml-MiniLM-L12-v2` line is required because the pre-cutover identity used a custom abbreviation ("ml" not "multilingual") that doesn't match the auto-derived identity from the model path. Without explicit IDENTITY, the override would dim-match but identity-mismatch on the next run.

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

Or restore the prior identity by setting all three env vars:

  export CASTLE_EMBEDDER_MODEL=<the model that produced '<stored_identity>'>
  export CASTLE_EMBEDDER_DIM=<stored_dim>
  export CASTLE_EMBEDDER_IDENTITY=<stored_identity>
```

The opt-out block names all 3 env vars (MODEL + DIM + IDENTITY) even though dim matches in this case, for consistency with the dim-mismatch error and to make the override block copy-pasteable as a self-contained set.

## Components (file-level changes)

| File | Change | LOC |
|---|---|---|
| `cognitive_castle/config.py` | Flip 3 defaults at lines 317, 338+343, 361. Rewrite the `embedder_identity` property to auto-derive from `embedder_model` when not explicitly set (env var or yaml override still wins). Update docstrings (lines 306-307, 325, 354) to name bge-m3 as the new default and document the auto-derive behavior. | +25, -10 |
| `cognitive_castle/backends/lancedb_backend.py` | Add `_check_embedder_compat(palace_path, cfg)` private method called from `__init__`. Implements: open `castle_drawers` if exists → dim check via PyArrow `FixedSizeList.list_size` → raise on mismatch. Then open `castle_metadata` if exists → identity check via `to_arrow()` + `pyarrow.compute.equal` → raise on mismatch. Helper `_read_stored_identity() -> Optional[str]`. Helper `_write_identity(s: str)`. Race-safe grandfather: wrap `db.create_table("castle_metadata", ...)` in `try/except`; on duplicate-table error, fall back to `db.open_table` + re-run identity check. Add `castle_metadata` table creation logic to the first-write path. Helpers `_dim_mismatch_message(stored_dim, cfg, palace_path)` and `_identity_mismatch_message(stored_identity, cfg, palace_path)` build the inline error messages. | +90 |
| `cognitive_castle/backends/base.py` | NO CHANGES. `EmbedderIdentityMismatchError` stays as the simple message-only exception. (Per Option 2 scope decision — inline construction at raise sites.) | 0 |
| `README.md` | Rewrite the existing "Going further: better recall with bge-m3" subsection (added by PR #1) as a "Migration from MiniLM (pre-cutover users)" subsection. Show the exact `castle reindex` command + the env-var override path (with the explicit `CASTLE_EMBEDDER_IDENTITY=paraphrase-ml-MiniLM-L12-v2` line). Update the Quickstart section if it names the embedder explicitly. | +30, -20 |
| `CLAUDE.md` | Update line 87 (file tree comment for `embedding.py`) + line 179 (retrieval pipeline diagram) to name bge-m3 as the default, not the alternative. | +3, -3 |
| `tests/test_config.py` | Update the 3 existing tests asserting MiniLM defaults (`test_embedder_model_default`, `test_embedder_dim_default`, `test_embedder_identity_default` or their actual names) to assert bge-m3 defaults instead. Add a small test asserting auto-derive when CASTLE_EMBEDDER_IDENTITY is unset. | +15, -5 |
| `tests/test_backends.py` (existing) or `tests/test_lancedb_identity_mismatch.py` (new) | 8 new tests for the wiring (see Testing section). | +160 |

**Total: ~330 LOC across 7 files** (3 are net-additions: backend logic + tests + README rewrite). No new modules.

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
| Concurrent grandfather: two processes both attempt `create_table("castle_metadata")` | Catch LanceDB's duplicate-table exception on the loser process, open the existing table, re-run identity check. The winning process's stamped identity becomes authoritative. |
| Config: user sets `CASTLE_EMBEDDER_MODEL` but not `CASTLE_EMBEDDER_IDENTITY` | Auto-derive identity from model (last `/` component). No error. |

## Testing

### 8 new tests in `tests/test_backends.py` (extension) or `tests/test_lancedb_identity_mismatch.py` (new file)

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


def test_concurrent_grandfather_is_race_safe(tmp_path, monkeypatch):
    """Two simultaneous backend inits on a legacy palace both succeed."""
    # Build palace via add(), DELETE castle_metadata to simulate legacy
    # Spawn two threads, each instantiating LanceDBBackend(palace_path, cfg) concurrently
    # Assert: exactly one wins the create_table race; the other catches the duplicate-table
    #         exception and opens the existing table; both backends end up functional;
    #         castle_metadata exists with exactly one embedder_identity row.


def test_identity_auto_derives_from_model_when_not_explicitly_set(monkeypatch):
    """When CASTLE_EMBEDDER_MODEL is set but CASTLE_EMBEDDER_IDENTITY is not, derive from model."""
    monkeypatch.setenv("CASTLE_EMBEDDER_MODEL", "BAAI/bge-large-en-v1.5")
    monkeypatch.delenv("CASTLE_EMBEDDER_IDENTITY", raising=False)
    cfg = CognitiveCastleConfig()
    assert cfg.embedder_identity == "bge-large-en-v1.5"

    # Explicit identity wins over auto-derive
    monkeypatch.setenv("CASTLE_EMBEDDER_IDENTITY", "custom-id")
    cfg = CognitiveCastleConfig()
    assert cfg.embedder_identity == "custom-id"
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

1. `pytest tests/test_backends.py -v -k "identity_mismatch"` (or the new test file) — **8 passed**.
2. `pytest tests/test_config.py -v -k "embedder"` — 3 default-value tests pass with the new bge-m3 values, AND the new auto-derive test passes.
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

1. **Placeholders:** None. Helper function names (`_check_embedder_compat`, `_read_stored_identity`, `_write_identity`, `_dim_mismatch_message`, `_identity_mismatch_message`) are concrete. PyArrow schema introspection code shown verbatim. Auto-derive property body shown verbatim.
2. **Internal consistency:** Architecture, Data Flow, Error Handling, Testing, and Acceptance all reference:
   - 3 config flips at exact `config.py` lines (317, 338+343, 361)
   - Two-layer check on `LanceDBBackend.__init__` (dim from PyArrow schema, identity from `castle_metadata` table via `to_arrow()` + `pyarrow.compute.equal`)
   - `castle_metadata` schema as `{key: utf8, value: utf8}`
   - Grandfather logic (write identity only if dim matches; race-safe via duplicate-table catch)
   - Auto-derive `cfg.embedder_identity` from `cfg.embedder_model` when not explicitly set
   - Inline error-message construction (Option 2 — no structured exception args)
   - Friendly error message format with migration command + 3-env-var override block
3. **Scope:** Single PR with 2 logically-coupled halves (defaults flip + safety net). Could decompose into 2 PRs but they're tightly coupled — flipping defaults without the safety net would break legacy users; wiring the safety net without flipping defaults would be a no-op for the current default. ~330 LOC fits in one PR.
4. **Ambiguity:** Grandfather logic stated in 3 places (Architecture, Data Flow, Error Handling table). LanceDB-native storage decision stated in Non-goals + Architecture. Option 2 inline-error-construction decision stated in Non-goals + Components row. Auto-derive identity stated in Architecture + Components row + Error Handling row + Testing.
5. **Empirical grounding:**
   - `embedder_model` / `embedder_dim` / `embedder_identity` defaults confirmed at `config.py:317, 338, 361` (verified via Read)
   - `EmbedderIdentityMismatchError` confirmed at `backends/base.py:53` + exported in `__init__.py` + zero call sites (verified via grep)
   - `vector` column's FixedSizeList type confirmed in `backends/lancedb_backend.py:80-95` (table schema)
   - PR #1's spec confirms cutover was deferred + dim-mismatch behavior was empirically verified
   - PR #4a's umbrella context confirms the safety-net wiring was queued as a follow-up

## Revision history

**Revision 2 (2026-05-13):** Second review pass surfaced 3 substantive issues. Fixed inline:
- **Real bug:** Layer 2 identity-check pseudocode used `table.search().where(...)`, which doesn't work on `castle_metadata` (no `vector` column → `.search()` API doesn't apply). Replaced with `to_arrow()` + `pyarrow.compute.equal` filter.
- **UX trap:** original spec required users changing `embedder_model` to ALSO change `embedder_identity` (silent stamp-with-wrong-identity risk). Added auto-derive: `cfg.embedder_identity` defaults to last `/` component of `cfg.embedder_model` when not explicitly set. Legacy MiniLM users (custom abbreviation in stored identity) are documented explicitly in the dim-mismatch error message.
- **Concurrency hole:** original spec's grandfather write was not race-safe. Two processes (interactive search + Stop-hook fire) hitting the same legacy palace could both attempt `create_table("castle_metadata")`. Added race-safe creation: catch LanceDB's duplicate-table exception on the loser, open the existing table, re-run identity check.

Also reflected as +2 tests (race-safety + auto-derive), +1 row each in Error Handling table and Components table, +50 LOC bump to total estimate (280 → 330).
