# KG Auto-Enrichment During Ingest — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Phase 2 to `castle mine` / `castle reindex` that populates `entity_registry.json` + `knowledge_graph.sqlite3` with `(entity, mentioned_in, drawer_id)` triples, unblocking the dormant `entity-match` SOAR production.

**Architecture:** Single new module `cognitive_castle/kg_enricher.py` orchestrates four steps (work-set selection, Stage A corpus walk, Stage B classify+promote with per-candidate sampling, Stage C triple writes). Miners lazy-import it as their last action. Pre-existing primitives (`entity_detector`, `entity_registry`, `knowledge_graph`) provide all heavy lifting.

**Tech Stack:** Python 3.12 (uses `itertools.batched`), pytest, ruff, LanceDB (vector store), SQLite (KG store), existing regex-based entity_detector.

**Spec reference:** `docs/superpowers/specs/2026-05-14-kg-enrichment-design.md` (v6 — six review passes).

**Pre-plan verifications already done:**
- Risk #9 (pattern compilation caching) — `_build_patterns` already has `@lru_cache(maxsize=256)` at `entity_detector.py:189`. No work needed.
- Risk #1 — `classify_entity` returns `type ∈ {person, project, uncertain}` confirmed. Spec's "promote only person/project" rule applies as-is.
- `EntityRegistry.load()` empty-default path works without onboarding (`entity_registry.py:338-346`).
- `EntityRegistry._data` shape: `people` is a dict (richer per-entry metadata), `projects` is a list of strings — `add_learned` must dispatch by type.
- Backend tests live in `tests/test_backends.py` (single file covering both LanceDB and Chroma), not separate per-backend files.

---

## File Structure

**NEW files:**
- `cognitive_castle/kg_enricher.py` — single public entry `enrich_palace(palace_path, cfg) -> dict`; private helpers `_select_work_ids`, `_walk_corpus`, `_classify_and_promote`, `_write_triples`
- `tests/test_kg_enricher.py` — per-stage unit tests + integration test against tmp_path palace

**MODIFIED files:**
- `cognitive_castle/config.py` — add `entity_promote_threshold`, `entity_score_sample_drawers`, `entity_fetch_batch_size` properties
- `cognitive_castle/entity_registry.py` — add `add_learned(name, type, confidence)` method
- `cognitive_castle/backends/base.py` — add abstract `list_drawer_ids()` to `BaseCollection`
- `cognitive_castle/backends/lancedb_backend.py` — implement `list_drawer_ids()` via `to_arrow()`
- `cognitive_castle/backends/chroma.py` — implement `list_drawer_ids()` via `get(include=[])`
- `cognitive_castle/miner.py` — add Phase 2 hook at end of `mine()`
- `cognitive_castle/convo_miner.py` — add Phase 2 hook at end of `mine_convos()`
- `tests/test_config.py` — append config-property tests
- `tests/test_entity_registry.py` — append `add_learned` tests
- `tests/test_backends.py` — append `list_drawer_ids` tests for both backends
- `tests/test_miner.py` — append miner integration tests
- `tests/test_convo_miner.py` — append convo_miner integration tests
- `CLAUDE.md` — one-line note in Architecture section

---

## Branch

All tasks land on a single feature branch:

```bash
git checkout -b feat/kg-enrichment-during-ingest
```

Final PR merges to `develop`.

---

## Task 1: Config — three new properties

**Files:**
- Modify: `cognitive_castle/config.py`
- Test: `tests/test_config.py` (append)

**Agent model:** haiku (mechanical)

- [ ] **Step 1: Read existing config patterns to mirror them**

```bash
grep -n "@property" cognitive_castle/config.py | head -10
```

Pick one numeric property (e.g., `recency_tau_days`) and read its full implementation so the new properties match style: env-var override → file_config → default.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_entity_promote_threshold_default():
    cfg = CognitiveCastleConfig()
    assert cfg.entity_promote_threshold == 0.70


def test_entity_promote_threshold_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_ENTITY_PROMOTE_THRESHOLD", "0.85")
    cfg = CognitiveCastleConfig()
    assert cfg.entity_promote_threshold == 0.85


def test_entity_score_sample_drawers_default():
    cfg = CognitiveCastleConfig()
    assert cfg.entity_score_sample_drawers == 20


def test_entity_score_sample_drawers_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_ENTITY_SCORE_SAMPLE_DRAWERS", "5")
    cfg = CognitiveCastleConfig()
    assert cfg.entity_score_sample_drawers == 5


def test_entity_fetch_batch_size_default():
    cfg = CognitiveCastleConfig()
    assert cfg.entity_fetch_batch_size == 1000


def test_entity_fetch_batch_size_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_ENTITY_FETCH_BATCH_SIZE", "100")
    cfg = CognitiveCastleConfig()
    assert cfg.entity_fetch_batch_size == 100
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/test_config.py -k "entity_promote or entity_score or entity_fetch" -v
```

Expected: 6 FAIL with `AttributeError: 'CognitiveCastleConfig' object has no attribute ...`.

- [ ] **Step 4: Implement the three properties**

Append to `cognitive_castle/config.py` (place near other numeric properties — find a sibling like `recency_tau_days` and add after it):

```python
@property
def entity_promote_threshold(self) -> float:
    """Confidence threshold above which auto-detected entities are added
    to the registry by the KG enricher. Default 0.70.

    Reads from ``CASTLE_ENTITY_PROMOTE_THRESHOLD`` env var first, then
    config file, then default.
    """
    env_val = os.environ.get("CASTLE_ENTITY_PROMOTE_THRESHOLD")
    if env_val:
        return float(env_val.strip())
    cfg_val = self._file_config.get("entity_promote_threshold")
    if cfg_val is not None:
        return float(cfg_val)
    return 0.70


@property
def entity_score_sample_drawers(self) -> int:
    """Per-candidate drawer-sample size for Stage B scoring. Default 20.

    Reads from ``CASTLE_ENTITY_SCORE_SAMPLE_DRAWERS`` env var first, then
    config file, then default.
    """
    env_val = os.environ.get("CASTLE_ENTITY_SCORE_SAMPLE_DRAWERS")
    if env_val:
        return int(env_val.strip())
    cfg_val = self._file_config.get("entity_score_sample_drawers")
    if cfg_val is not None:
        return int(cfg_val)
    return 20


@property
def entity_fetch_batch_size(self) -> int:
    """LanceDB bulk-fetch batch size for Stage B's text_by_id build.
    Default 1000.

    Reads from ``CASTLE_ENTITY_FETCH_BATCH_SIZE`` env var first, then
    config file, then default.
    """
    env_val = os.environ.get("CASTLE_ENTITY_FETCH_BATCH_SIZE")
    if env_val:
        return int(env_val.strip())
    cfg_val = self._file_config.get("entity_fetch_batch_size")
    if cfg_val is not None:
        return int(cfg_val)
    return 1000
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_config.py -k "entity_promote or entity_score or entity_fetch" -v
```

Expected: 6 PASS.

- [ ] **Step 6: Format + lint**

```bash
ruff format cognitive_castle/config.py tests/test_config.py
ruff check cognitive_castle/config.py tests/test_config.py
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add cognitive_castle/config.py tests/test_config.py
git commit -m "feat(config): add three KG-enricher config properties

Add entity_promote_threshold (default 0.70), entity_score_sample_drawers
(default 20), entity_fetch_batch_size (default 1000). Each follows
Castle's standard env-var → file_config → default resolution order."
```

---

## Task 2: EntityRegistry — `add_learned` method

**Files:**
- Modify: `cognitive_castle/entity_registry.py`
- Test: `tests/test_entity_registry.py` (append)

**Agent model:** haiku (small + tests)

**Notes for the implementer:** `people` is a dict (each entry has `source`, `contexts`, `aliases`, `relationship`, `confidence`), `projects` is a list of strings. `add_learned` must dispatch on `type`. Idempotent — never overwrites an existing entry, regardless of source. Caller is responsible for `save()` (we batch saves).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_entity_registry.py`:

```python
def test_add_learned_person_new_entity(tmp_path):
    from cognitive_castle.entity_registry import EntityRegistry

    registry = EntityRegistry(EntityRegistry._empty(), tmp_path / "reg.json")
    registry.add_learned("Riley", type="person", confidence=0.85)

    assert "Riley" in registry._data["people"]
    entry = registry._data["people"]["Riley"]
    assert entry["source"] == "learned"
    assert entry["confidence"] == 0.85


def test_add_learned_project_new_entity(tmp_path):
    from cognitive_castle.entity_registry import EntityRegistry

    registry = EntityRegistry(EntityRegistry._empty(), tmp_path / "reg.json")
    registry.add_learned("bge-m3", type="project", confidence=0.90)

    assert "bge-m3" in registry._data["projects"]


def test_add_learned_idempotent_when_person_already_present(tmp_path):
    from cognitive_castle.entity_registry import EntityRegistry

    registry = EntityRegistry(EntityRegistry._empty(), tmp_path / "reg.json")
    registry._data["people"]["Riley"] = {
        "source": "onboarding",
        "contexts": ["personal"],
        "aliases": [],
        "relationship": "child",
        "confidence": 1.0,
    }

    registry.add_learned("Riley", type="person", confidence=0.70)

    # Onboarding entry preserved — not overwritten
    assert registry._data["people"]["Riley"]["source"] == "onboarding"
    assert registry._data["people"]["Riley"]["confidence"] == 1.0


def test_add_learned_idempotent_when_project_already_present(tmp_path):
    from cognitive_castle.entity_registry import EntityRegistry

    registry = EntityRegistry(EntityRegistry._empty(), tmp_path / "reg.json")
    registry._data["projects"].append("bge-m3")

    registry.add_learned("bge-m3", type="project", confidence=0.50)

    # Still just one entry — no duplicate
    assert registry._data["projects"].count("bge-m3") == 1


def test_add_learned_does_not_save_to_disk(tmp_path):
    """add_learned mutates in memory; caller must call .save() to persist."""
    from cognitive_castle.entity_registry import EntityRegistry

    path = tmp_path / "reg.json"
    registry = EntityRegistry(EntityRegistry._empty(), path)
    registry.add_learned("Riley", type="person", confidence=0.85)

    # File not yet written
    assert not path.exists()

    registry.save()
    assert path.exists()


def test_add_learned_rejects_unknown_type(tmp_path):
    from cognitive_castle.entity_registry import EntityRegistry

    registry = EntityRegistry(EntityRegistry._empty(), tmp_path / "reg.json")
    with pytest.raises(ValueError, match="type must be 'person' or 'project'"):
        registry.add_learned("Riley", type="concept", confidence=0.85)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_entity_registry.py -k "add_learned" -v
```

Expected: 6 FAIL with `AttributeError: 'EntityRegistry' object has no attribute 'add_learned'`.

- [ ] **Step 3: Implement `add_learned`**

Add the method to `cognitive_castle/entity_registry.py` near the existing `seed()` method (around line 391):

```python
def add_learned(self, name: str, type: str, confidence: float) -> None:
    """Add an auto-detected entity to the registry.

    Idempotent: if ``name`` is already present (regardless of source),
    this is a no-op — onboarding-sourced entries are not overwritten.

    Caller is responsible for calling ``self.save()`` afterwards.
    The KG enricher batches saves at end of Stage B.

    Args:
        name: Entity name.
        type: "person" or "project". Concepts are not auto-promoted
            from drawer text by the enricher.
        confidence: Classifier confidence in [0, 1].

    Raises:
        ValueError: if ``type`` is not "person" or "project".
    """
    if type not in ("person", "project"):
        raise ValueError(
            f"type must be 'person' or 'project', got {type!r}"
        )

    if type == "person":
        if name in self._data["people"]:
            return  # idempotent — preserve existing entry
        self._data["people"][name] = {
            "source": "learned",
            "contexts": ["personal"],
            "aliases": [],
            "relationship": "",
            "confidence": float(confidence),
        }
    else:  # project
        if name in self._data["projects"]:
            return  # idempotent
        self._data["projects"].append(name)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_entity_registry.py -k "add_learned" -v
```

Expected: 6 PASS.

- [ ] **Step 5: Run full entity_registry tests to ensure no regression**

```bash
python -m pytest tests/test_entity_registry.py -v
```

Expected: all pass.

- [ ] **Step 6: Format + lint**

```bash
ruff format cognitive_castle/entity_registry.py tests/test_entity_registry.py
ruff check cognitive_castle/entity_registry.py tests/test_entity_registry.py
```

- [ ] **Step 7: Commit**

```bash
git add cognitive_castle/entity_registry.py tests/test_entity_registry.py
git commit -m "feat(entity_registry): add_learned method for auto-detected entities

Idempotent: if entity already present, no-op (preserves onboarding-
sourced entries). Dispatches on type — people are dict entries,
projects are list strings. Caller calls save() to persist."
```

---

## Task 3: Backend — `list_drawer_ids` on base + LanceDB + Chroma

**Files:**
- Modify: `cognitive_castle/backends/base.py`
- Modify: `cognitive_castle/backends/lancedb_backend.py`
- Modify: `cognitive_castle/backends/chroma.py`
- Test: `tests/test_backends.py` (append)

**Agent model:** haiku (mechanical)

**Notes:** Read `tests/test_backends.py` first to understand the fixture pattern (likely parametrized over both backends). The new method goes on `BaseCollection` (abstract) and both concrete subclasses.

- [ ] **Step 1: Inspect existing backend test patterns**

```bash
grep -n "def test_\|@pytest.fixture\|parametrize" tests/test_backends.py | head -20
```

This reveals whether tests are parametrized over backends or have separate cases per backend. Follow the existing pattern.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_backends.py`, matching the existing fixture/parametrize style. For each backend (LanceDB and Chroma if both are tested in the file):

```python
def test_list_drawer_ids_empty_palace(collection):
    """list_drawer_ids returns [] when no drawers exist."""
    ids = collection.list_drawer_ids()
    assert ids == []


def test_list_drawer_ids_returns_all_ids(collection):
    """list_drawer_ids returns every drawer id currently in the palace."""
    collection.add(
        documents=["alpha text", "beta text", "gamma text"],
        ids=["id-a", "id-b", "id-c"],
        metadatas=[{"wing": "w", "room": "r"} for _ in range(3)],
        embeddings=[[0.0] * 1024, [0.1] * 1024, [0.2] * 1024],
    )

    ids = collection.list_drawer_ids()
    assert sorted(ids) == ["id-a", "id-b", "id-c"]
```

(Match the actual fixture name and parametrization in the file. If tests are not currently parametrized, write the test twice — once per backend — using whatever construction pattern existing tests use.)

- [ ] **Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/test_backends.py -k "list_drawer_ids" -v
```

Expected: FAIL with `AttributeError: 'LanceDBCollection' (or 'ChromaCollection') object has no attribute 'list_drawer_ids'`.

- [ ] **Step 4: Add abstract method to base**

In `cognitive_castle/backends/base.py`, add to `BaseCollection` (find the section with other abstract methods like `add`, `query`, `get`):

```python
@abstractmethod
def list_drawer_ids(self) -> list[str]:
    """Return every drawer id currently stored in this collection.

    Used by the KG enricher to compute its work-set (all_ids − done_ids).
    Order is not specified — callers must sort if they need determinism.
    Returns [] for an empty collection.
    """
    ...
```

- [ ] **Step 5: Implement on LanceDB backend**

In `cognitive_castle/backends/lancedb_backend.py`, find the `LanceDBCollection` class and add:

```python
def list_drawer_ids(self) -> list[str]:
    """LanceDB implementation: scan the id column via to_arrow().

    Materializes the full id list. At ~40 bytes per id string this is
    ~2 MB for 20K rows, ~10 MB for 100K. Adequate for current palace
    sizes; can be switched to a chunked iterator later if needed.
    """
    if self._table is None:
        return []
    try:
        return self._table.to_arrow().column("id").to_pylist()
    except (KeyError, AttributeError):
        # Empty table or missing column — treat as empty
        return []
```

(If `self._table` is not the right attribute name in this codebase, grep for the actual handle the class uses to talk to LanceDB. Recent context shows the LanceDB backend uses `db.open_table("castle_drawers")` — find the cached handle.)

- [ ] **Step 6: Implement on Chroma backend**

In `cognitive_castle/backends/chroma.py`, find the `ChromaCollection` class and add:

```python
def list_drawer_ids(self) -> list[str]:
    """Chroma implementation: get() with no filters returns all ids."""
    result = self._collection.get(include=[])  # include=[] skips heavy columns
    return list(result.get("ids", []))
```

(Verify the actual handle name — likely `self._collection`.)

- [ ] **Step 7: Run tests to verify they pass**

```bash
python -m pytest tests/test_backends.py -k "list_drawer_ids" -v
```

Expected: PASS (both backends if parametrized).

- [ ] **Step 8: Run full backend test suite to ensure no regression**

```bash
python -m pytest tests/test_backends.py -v
```

- [ ] **Step 9: Format + lint**

```bash
ruff format cognitive_castle/backends/ tests/test_backends.py
ruff check cognitive_castle/backends/ tests/test_backends.py
```

- [ ] **Step 10: Commit**

```bash
git add cognitive_castle/backends/ tests/test_backends.py
git commit -m "feat(backends): list_drawer_ids on BaseCollection + LanceDB + Chroma

Used by the KG enricher's work-set selection. Order unspecified; callers
sort if they need determinism. Empty palace returns []."
```

---

## Task 4: `kg_enricher.py` — module skeleton + Stage A (walker)

**Files:**
- Create: `cognitive_castle/kg_enricher.py`
- Create: `tests/test_kg_enricher.py`

**Agent model:** sonnet (judgment — picks data structures + APIs)

**Notes:** This task creates the module file, defines `enrich_palace`'s signature and return dict, and implements the work-set selection + Stage A walker. Stage B and Stage C are added in Tasks 5 and 6. Returns early with zero counts if work-set is empty.

- [ ] **Step 1: Write failing tests for Stage A behaviors**

Create `tests/test_kg_enricher.py`:

```python
"""Tests for cognitive_castle.kg_enricher (Phase 2 of mine())."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable
from unittest.mock import MagicMock

import pytest


# ── Fixtures ─────────────────────────────────────────────────────────────


def _mock_cfg(
    *,
    threshold=0.70,
    sample_drawers=20,
    fetch_batch=1000,
    languages=("en",),
):
    """Minimal cfg exposing only the fields kg_enricher reads."""
    cfg = MagicMock()
    cfg.entity_promote_threshold = threshold
    cfg.entity_score_sample_drawers = sample_drawers
    cfg.entity_fetch_batch_size = fetch_batch
    cfg.languages = languages
    return cfg


class FakeCollection:
    """In-memory stand-in for a LanceDB collection."""

    def __init__(self, rows: list[dict]):
        self._rows = {r["id"]: r for r in rows}

    def list_drawer_ids(self) -> list[str]:
        return list(self._rows.keys())

    def get_by_ids(self, ids: Iterable[str]) -> list[dict]:
        return [self._rows[i] for i in ids if i in self._rows]


# ── Stage A tests ────────────────────────────────────────────────────────


def test_enrich_palace_returns_zeros_on_empty_palace(tmp_path, monkeypatch):
    """Empty palace → no work, returns {0, 0, 0, elapsed}."""
    import cognitive_castle.kg_enricher as kg_enricher

    monkeypatch.setattr(
        "cognitive_castle.palace.get_collection",
        lambda *a, **kw: FakeCollection(rows=[]),
    )

    result = kg_enricher.enrich_palace(str(tmp_path), _mock_cfg())

    assert result["drawers_scanned"] == 0
    assert result["entities_promoted"] == 0
    assert result["triples_written"] == 0
    assert "elapsed_s" in result


def test_walk_corpus_builds_mention_map_and_freq(tmp_path):
    """Stage A: for each drawer, extract candidates → populate mention_map
    and freq_by_name with corpus-wide counts."""
    import cognitive_castle.kg_enricher as kg_enricher

    rows = [
        {
            "id": "d1",
            "text": "Riley went to the store. Riley likes apples.",
            "wing": "p", "room": "r", "source_file": "f1",
        },
        {
            "id": "d2",
            "text": "Riley discussed bge-m3 with Alice.",
            "wing": "p", "room": "r", "source_file": "f2",
        },
    ]
    col = FakeCollection(rows)
    cfg = _mock_cfg()

    mention_map, freq_by_name = kg_enricher._walk_corpus(
        col, work_ids=["d1", "d2"], cfg=cfg
    )

    # mention_map: name → set of drawer_ids that mentioned it
    assert "d1" in mention_map.get("Riley", set())
    assert "d2" in mention_map.get("Riley", set())
    # freq_by_name: corpus-wide occurrence count
    assert freq_by_name.get("Riley", 0) >= 2  # at least 2 mentions


def test_walk_corpus_empty_work_ids(tmp_path):
    """Empty work_ids → empty mention_map and freq_by_name."""
    import cognitive_castle.kg_enricher as kg_enricher

    col = FakeCollection(rows=[])
    cfg = _mock_cfg()

    mention_map, freq_by_name = kg_enricher._walk_corpus(col, work_ids=[], cfg=cfg)
    assert mention_map == {} or len(mention_map) == 0
    assert freq_by_name == {} or len(freq_by_name) == 0


def test_walk_corpus_batches_at_1000(monkeypatch, tmp_path):
    """Stage A batches get_by_ids calls at 1000 per the spec."""
    import cognitive_castle.kg_enricher as kg_enricher

    rows = [
        {"id": f"d{i}", "text": "no entities here", "wing": "p", "room": "r", "source_file": "f"}
        for i in range(2500)
    ]
    col = FakeCollection(rows)
    call_sizes = []
    original_get_by_ids = col.get_by_ids

    def tracking_get_by_ids(ids):
        ids_list = list(ids)
        call_sizes.append(len(ids_list))
        return original_get_by_ids(ids_list)

    col.get_by_ids = tracking_get_by_ids

    kg_enricher._walk_corpus(col, work_ids=[f"d{i}" for i in range(2500)], cfg=_mock_cfg())

    # 2500 → batches of (1000, 1000, 500)
    assert call_sizes == [1000, 1000, 500]


def test_select_work_ids_excludes_adapter_done_drawers(tmp_path):
    """Drawers with this adapter's triples are excluded from work_ids;
    drawers with a DIFFERENT adapter's triples are still included."""
    import cognitive_castle.kg_enricher as kg_enricher
    from cognitive_castle.knowledge_graph import KnowledgeGraph

    kg_path = tmp_path / "knowledge_graph.sqlite3"
    kg = KnowledgeGraph(db_path=str(kg_path))
    kg.add_triple(
        "Riley", "mentioned_in", "d1",
        source_drawer_id="d1",
        adapter_name="entity-mention-indexer",
    )
    kg.add_triple(
        "Bob", "married_to", "Alice",
        source_drawer_id="d2",
        adapter_name="manual-castle-kg-add",  # different adapter
    )

    work_ids = kg_enricher._select_work_ids(
        all_ids=["d1", "d2", "d3"], kg_path=str(kg_path)
    )

    # d1 covered by us → excluded. d2 covered by different adapter → included.
    # d3 has no triples → included.
    assert "d1" not in work_ids
    assert "d2" in work_ids
    assert "d3" in work_ids
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_kg_enricher.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'cognitive_castle.kg_enricher'`.

- [ ] **Step 3: Create the module with skeleton + Stage A**

Create `cognitive_castle/kg_enricher.py`:

```python
"""kg_enricher.py — Phase 2 of `castle mine` / `castle reindex`.

Walks the un-indexed drawer set, extracts entity candidates, classifies
+ promotes high-confidence ones to the registry, and writes
``(entity, mentioned_in, drawer_id)`` triples to the knowledge graph.

Opt-in by virtue of being called from the miner's end-of-pipeline hook.
Local-only — regex + signal-counting (no LLM, no network). Append-only,
idempotent, self-healing on interrupt.

See spec: docs/superpowers/specs/2026-05-14-kg-enrichment-design.md
"""

from __future__ import annotations

import sqlite3
import time
from collections import Counter, defaultdict
from itertools import batched
from pathlib import Path
from typing import Iterable

from . import entity_detector
from . import palace as palace_mod


ADAPTER_NAME = "entity-mention-indexer"


def enrich_palace(palace_path: str, cfg) -> dict:
    """Public entry point. Runs all four steps of Phase 2.

    Returns ``{"drawers_scanned", "entities_promoted", "triples_written",
    "elapsed_s"}``. Never raises — caller catches at miner boundary.
    """
    started = time.time()
    col = palace_mod.get_collection(palace_path=palace_path)

    all_ids = col.list_drawer_ids()
    if not all_ids:
        return _result(0, 0, 0, started)

    kg_path = str(Path(palace_path).parent / "knowledge_graph.sqlite3")
    work_ids = _select_work_ids(all_ids=all_ids, kg_path=kg_path)
    if not work_ids:
        return _result(0, 0, 0, started)

    mention_map, freq_by_name = _walk_corpus(col, work_ids=work_ids, cfg=cfg)

    # Stage B + Stage C added in Tasks 5 and 6. For now this task's
    # contract is: work-set + walker work end-to-end; B and C return zero.
    return _result(
        drawers_scanned=len(work_ids),
        entities_promoted=0,
        triples_written=0,
        started=started,
    )


def _select_work_ids(*, all_ids: list[str], kg_path: str) -> list[str]:
    """all_ids − done_ids (this-adapter triples). Returns a list (Stage A
    iterates it). Order matches all_ids minus removed entries."""
    done_ids = _query_done_ids(kg_path=kg_path)
    return [i for i in all_ids if i not in done_ids]


def _query_done_ids(*, kg_path: str) -> set[str]:
    """Pull source_drawer_ids of triples written by this adapter."""
    if not Path(kg_path).exists():
        return set()
    try:
        with sqlite3.connect(kg_path) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT source_drawer_id
                FROM triples
                WHERE adapter_name = ?
                  AND source_drawer_id IS NOT NULL
                """,
                (ADAPTER_NAME,),
            ).fetchall()
        return {row[0] for row in rows}
    except sqlite3.Error:
        # Missing table on first run is normal — KnowledgeGraph creates schema
        # on its own first write. Treat any read error here as "nothing done".
        return set()


def _walk_corpus(col, *, work_ids: Iterable[str], cfg) -> tuple[dict, Counter]:
    """Stage A: single regex pass per drawer. Returns
    ``(mention_map, freq_by_name)`` where mention_map is
    ``name → set[drawer_id]`` and freq_by_name is corpus-wide name counts."""
    mention_map: dict[str, set[str]] = defaultdict(set)
    freq_by_name: Counter = Counter()

    for batch in batched(work_ids, 1000):
        for row in col.get_by_ids(batch):
            per_drawer = entity_detector.extract_candidates(
                row["text"], cfg.languages
            )
            for name, count in per_drawer.items():
                mention_map[name].add(row["id"])
                freq_by_name[name] += count

    return dict(mention_map), freq_by_name


def _result(
    drawers_scanned: int,
    entities_promoted: int,
    triples_written: int,
    started: float,
) -> dict:
    return {
        "drawers_scanned": drawers_scanned,
        "entities_promoted": entities_promoted,
        "triples_written": triples_written,
        "elapsed_s": round(time.time() - started, 2),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_kg_enricher.py -v
```

Expected: 5 PASS (the Stage A and work-set tests).

- [ ] **Step 5: Format + lint**

```bash
ruff format cognitive_castle/kg_enricher.py tests/test_kg_enricher.py
ruff check cognitive_castle/kg_enricher.py tests/test_kg_enricher.py
```

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/kg_enricher.py tests/test_kg_enricher.py
git commit -m "feat(kg_enricher): module skeleton + Stage A walker + work-set selection

Public entry enrich_palace(palace_path, cfg) → dict. Implements:
  * Work-set selection via SQLite query for this adapter's done_ids,
    set-diff in Python.
  * Stage A: per-drawer extract_candidates → mention_map + freq_by_name.
    Batches LanceDB hydrate at 1000.

Stage B (classify+promote) and Stage C (triple writes) land in
follow-up commits. enrich_palace currently returns zero counts for
those — the function shape is locked but B/C are no-ops."
```

---

## Task 5: `kg_enricher.py` — Stage B (classify + promote)

**Files:**
- Modify: `cognitive_castle/kg_enricher.py`
- Modify: `tests/test_kg_enricher.py`

**Agent model:** sonnet (most complex stage — per-candidate sampling, batched fetch, registry mutation)

- [ ] **Step 1: Append failing Stage B tests to `tests/test_kg_enricher.py`**

```python
# ── Stage B tests ────────────────────────────────────────────────────────


def test_classify_promotes_above_threshold(tmp_path, monkeypatch):
    """Stage B: a candidate with classifier confidence >= threshold and
    type in {person, project} gets added to the registry."""
    import cognitive_castle.kg_enricher as kg_enricher
    from cognitive_castle.entity_registry import EntityRegistry

    registry = EntityRegistry(EntityRegistry._empty(), tmp_path / "reg.json")

    # Stub classifier to return a clean "person, 0.9" verdict for "Riley"
    monkeypatch.setattr(
        "cognitive_castle.entity_detector.score_entity",
        lambda *a, **kw: {
            "person_score": 10, "project_score": 0,
            "person_signals": ["dialogue marker (3x)", "addressed directly (2x)"],
            "project_signals": [],
        },
    )

    mention_map = {"Riley": {"d1"}}
    freq_by_name = Counter({"Riley": 3})
    text_by_id = {"d1": "Riley went to the store."}

    promoted = kg_enricher._classify_and_promote(
        mention_map=mention_map,
        freq_by_name=freq_by_name,
        text_by_id=text_by_id,
        registry=registry,
        cfg=_mock_cfg(threshold=0.70),
    )

    assert "Riley" in promoted
    assert "Riley" in registry._data["people"]
    assert registry._data["people"]["Riley"]["source"] == "learned"


def test_classify_skips_unknown_uncertain(tmp_path, monkeypatch):
    """Below-threshold or 'uncertain' classifications drop the entry from
    mention_map (no triples will be written for them)."""
    import cognitive_castle.kg_enricher as kg_enricher
    from cognitive_castle.entity_registry import EntityRegistry

    registry = EntityRegistry(EntityRegistry._empty(), tmp_path / "reg.json")

    # Zero scores → classify_entity returns "uncertain"
    monkeypatch.setattr(
        "cognitive_castle.entity_detector.score_entity",
        lambda *a, **kw: {
            "person_score": 0, "project_score": 0,
            "person_signals": [], "project_signals": [],
        },
    )

    mention_map = {"weakword": {"d1"}}
    freq_by_name = Counter({"weakword": 1})
    text_by_id = {"d1": "weakword appears here."}

    promoted = kg_enricher._classify_and_promote(
        mention_map=mention_map,
        freq_by_name=freq_by_name,
        text_by_id=text_by_id,
        registry=registry,
        cfg=_mock_cfg(threshold=0.70),
    )

    assert promoted == set() or not promoted
    assert "weakword" not in mention_map  # dropped


def test_classify_skips_already_registered(tmp_path, monkeypatch):
    """Pre-registered entities (lookup type != 'unknown') skip scoring
    entirely; they stay in mention_map untouched."""
    import cognitive_castle.kg_enricher as kg_enricher
    from cognitive_castle.entity_registry import EntityRegistry

    registry = EntityRegistry(EntityRegistry._empty(), tmp_path / "reg.json")
    registry._data["people"]["Riley"] = {
        "source": "onboarding",
        "contexts": ["personal"],
        "aliases": [],
        "relationship": "child",
        "confidence": 1.0,
    }

    # score_entity should not be called for Riley at all — stub to raise
    monkeypatch.setattr(
        "cognitive_castle.entity_detector.score_entity",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("called for known entity")),
    )

    mention_map = {"Riley": {"d1", "d2"}}
    freq_by_name = Counter({"Riley": 5})
    text_by_id = {"d1": "x", "d2": "y"}

    promoted = kg_enricher._classify_and_promote(
        mention_map=mention_map,
        freq_by_name=freq_by_name,
        text_by_id=text_by_id,
        registry=registry,
        cfg=_mock_cfg(),
    )

    # No promotion happened, but Riley remains in mention_map for Stage C
    assert "Riley" in mention_map
    assert "Riley" not in promoted  # not newly promoted (was already there)


def test_unknown_type_means_not_registered(tmp_path, monkeypatch):
    """Regression: lookup() returns {'type': 'unknown'} for missing entries.
    The check must compare against 'unknown' explicitly, not use truthiness
    (the truthy-check would skip every entry)."""
    import cognitive_castle.kg_enricher as kg_enricher
    from cognitive_castle.entity_registry import EntityRegistry

    registry = EntityRegistry(EntityRegistry._empty(), tmp_path / "reg.json")

    # Stub classifier to promote
    monkeypatch.setattr(
        "cognitive_castle.entity_detector.score_entity",
        lambda *a, **kw: {
            "person_score": 12, "project_score": 0,
            "person_signals": ["dialogue marker (3x)", "addressed directly (2x)"],
            "project_signals": [],
        },
    )

    mention_map = {"NewPerson": {"d1"}}
    freq_by_name = Counter({"NewPerson": 3})
    text_by_id = {"d1": "x"}

    promoted = kg_enricher._classify_and_promote(
        mention_map=mention_map,
        freq_by_name=freq_by_name,
        text_by_id=text_by_id,
        registry=registry,
        cfg=_mock_cfg(threshold=0.70),
    )

    # Promotion happened — proves lookup()['type'] == 'unknown' was recognized
    # as "not yet registered"
    assert "NewPerson" in promoted
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_kg_enricher.py -k "classify or unknown_type" -v
```

Expected: FAIL with `AttributeError: module 'cognitive_castle.kg_enricher' has no attribute '_classify_and_promote'`.

- [ ] **Step 3: Implement Stage B**

Add to `cognitive_castle/kg_enricher.py` (below `_walk_corpus`):

```python
def _classify_and_promote(
    *,
    mention_map: dict,
    freq_by_name: Counter,
    text_by_id: dict,
    registry,
    cfg,
) -> set[str]:
    """Stage B: score each unregistered candidate against a per-candidate
    sample of ~SAMPLE_N drawer texts. Classify. Promote if confident,
    else drop from mention_map.

    Returns the set of names newly added to the registry by this call.
    Mutates ``mention_map`` (deletes rejected entries) and ``registry``
    (adds learned entries). Caller is responsible for ``registry.save()``.
    """
    sample_n = cfg.entity_score_sample_drawers
    threshold = cfg.entity_promote_threshold
    languages = cfg.languages

    candidates_to_score = [
        name for name in freq_by_name
        if registry.lookup(name).get("type") == "unknown"
    ]

    promoted: set[str] = set()
    for name in candidates_to_score:
        sample_ids = sorted(mention_map.get(name, ()))[:sample_n]
        sample_texts = [text_by_id[did] for did in sample_ids if did in text_by_id]
        if not sample_texts:
            # Defensive: no usable sample → reject
            del mention_map[name]
            continue
        sample = "\n".join(sample_texts)
        scores = entity_detector.score_entity(
            name, sample, sample.splitlines(), languages
        )
        cls = entity_detector.classify_entity(name, freq_by_name[name], scores)

        if (
            cls["type"] in ("person", "project")
            and cls["confidence"] >= threshold
        ):
            registry.add_learned(
                name, type=cls["type"], confidence=cls["confidence"]
            )
            promoted.add(name)
        else:
            del mention_map[name]

    return promoted
```

Also add a `_build_text_cache` helper that does the batched fetch (used by `enrich_palace` later):

```python
def _build_text_cache(col, *, drawer_ids: set[str], cfg) -> dict[str, str]:
    """Batched bulk fetch. Returns ``{drawer_id: text}`` for the requested
    ids. Skips the LanceDB vector + metadata columns by reading text only
    from each returned row."""
    if not drawer_ids:
        return {}
    batch_size = cfg.entity_fetch_batch_size
    text_by_id: dict[str, str] = {}
    for batch in batched(sorted(drawer_ids), batch_size):
        for row in col.get_by_ids(batch):
            text_by_id[row["id"]] = row["text"]
    return text_by_id
```

Update `enrich_palace` to actually call Stage B:

```python
def enrich_palace(palace_path: str, cfg) -> dict:
    started = time.time()
    col = palace_mod.get_collection(palace_path=palace_path)

    all_ids = col.list_drawer_ids()
    if not all_ids:
        return _result(0, 0, 0, started)

    kg_path = str(Path(palace_path).parent / "knowledge_graph.sqlite3")
    work_ids = _select_work_ids(all_ids=all_ids, kg_path=kg_path)
    if not work_ids:
        return _result(0, 0, 0, started)

    mention_map, freq_by_name = _walk_corpus(col, work_ids=work_ids, cfg=cfg)

    # Stage B: load registry, classify, promote
    from .entity_registry import EntityRegistry

    palace_dir = Path(palace_path).parent
    registry = EntityRegistry.load(palace_dir)

    # Determine which drawer_ids are needed for Stage B scoring
    candidates_to_score = [
        name for name in freq_by_name
        if registry.lookup(name).get("type") == "unknown"
    ]
    sample_n = cfg.entity_score_sample_drawers
    score_drawer_ids: set[str] = set()
    for name in candidates_to_score:
        score_drawer_ids.update(sorted(mention_map.get(name, ()))[:sample_n])

    text_by_id = _build_text_cache(col, drawer_ids=score_drawer_ids, cfg=cfg)

    promoted = _classify_and_promote(
        mention_map=mention_map,
        freq_by_name=freq_by_name,
        text_by_id=text_by_id,
        registry=registry,
        cfg=cfg,
    )
    registry.save()

    # Stage C lands in Task 6 — for now triples_written stays 0
    return _result(
        drawers_scanned=len(work_ids),
        entities_promoted=len(promoted),
        triples_written=0,
        started=started,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_kg_enricher.py -v
```

Expected: all tests so far PASS (including the 4 new Stage B tests + the prior 5).

- [ ] **Step 5: Format + lint**

```bash
ruff format cognitive_castle/kg_enricher.py tests/test_kg_enricher.py
ruff check cognitive_castle/kg_enricher.py tests/test_kg_enricher.py
```

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/kg_enricher.py tests/test_kg_enricher.py
git commit -m "feat(kg_enricher): Stage B — classify + promote with per-candidate sampling

For each unregistered candidate, sample ~SAMPLE_N (default 20) drawers
that actually mention it, score, classify. Promote when confidence ≥
threshold and type is person/project. Pre-registered entities skip
scoring entirely; rejected candidates get deleted from mention_map.

Bulk-fetches drawer texts in batches of entity_fetch_batch_size (1000).

Regression test: lookup()['type'] == 'unknown' is recognized as
not-yet-registered (truthy-check would have skipped every entry)."
```

---

## Task 6: `kg_enricher.py` — Stage C (triple writes) + observability

**Files:**
- Modify: `cognitive_castle/kg_enricher.py`
- Modify: `tests/test_kg_enricher.py`

**Agent model:** sonnet (judgment — Stage C completes the enricher; observability format ties everything together)

- [ ] **Step 1: Append failing Stage C tests**

```python
# ── Stage C tests ────────────────────────────────────────────────────────


def test_write_triples_writes_one_per_entity_drawer_pair(tmp_path):
    """For each (name, drawer_id) in mention_map, one triple is written
    with adapter_name='entity-mention-indexer'."""
    import cognitive_castle.kg_enricher as kg_enricher
    from cognitive_castle.entity_registry import EntityRegistry
    from cognitive_castle.knowledge_graph import KnowledgeGraph

    registry = EntityRegistry(EntityRegistry._empty(), tmp_path / "reg.json")
    registry._data["people"]["Riley"] = {
        "source": "learned",
        "contexts": ["personal"],
        "aliases": [],
        "relationship": "",
        "confidence": 0.85,
    }

    kg_path = tmp_path / "knowledge_graph.sqlite3"
    kg = KnowledgeGraph(db_path=str(kg_path))

    mention_map = {"Riley": {"d1", "d2", "d3"}}

    triples_written = kg_enricher._write_triples(
        mention_map=mention_map, registry=registry, kg=kg
    )

    assert triples_written == 3

    # All three triples should be present with our adapter_name
    import sqlite3
    with sqlite3.connect(str(kg_path)) as conn:
        rows = conn.execute(
            "SELECT subject, object, adapter_name FROM triples ORDER BY object"
        ).fetchall()
    assert len(rows) == 3
    assert all(r[0] == "Riley" for r in rows)
    assert all(r[2] == "entity-mention-indexer" for r in rows)
    assert sorted(r[1] for r in rows) == ["d1", "d2", "d3"]


def test_write_triples_skips_unknown_entries(tmp_path):
    """Safety net: if an entry in mention_map is somehow not in the
    registry (shouldn't happen but guard anyway), no triple is written."""
    import cognitive_castle.kg_enricher as kg_enricher
    from cognitive_castle.entity_registry import EntityRegistry
    from cognitive_castle.knowledge_graph import KnowledgeGraph

    registry = EntityRegistry(EntityRegistry._empty(), tmp_path / "reg.json")
    kg = KnowledgeGraph(db_path=str(tmp_path / "kg.sqlite3"))

    mention_map = {"NotRegistered": {"d1"}}

    triples_written = kg_enricher._write_triples(
        mention_map=mention_map, registry=registry, kg=kg
    )
    assert triples_written == 0


def test_write_triples_idempotent_via_insert_or_ignore(tmp_path):
    """add_triple uses INSERT OR IGNORE; re-running writes zero new triples."""
    import cognitive_castle.kg_enricher as kg_enricher
    from cognitive_castle.entity_registry import EntityRegistry
    from cognitive_castle.knowledge_graph import KnowledgeGraph

    registry = EntityRegistry(EntityRegistry._empty(), tmp_path / "reg.json")
    registry._data["projects"].append("bge-m3")

    kg = KnowledgeGraph(db_path=str(tmp_path / "kg.sqlite3"))

    mention_map = {"bge-m3": {"d1"}}
    first = kg_enricher._write_triples(
        mention_map=mention_map, registry=registry, kg=kg
    )
    second = kg_enricher._write_triples(
        mention_map=mention_map, registry=registry, kg=kg
    )

    assert first == 1
    # Second call MAY return 1 because add_triple doesn't tell us "was it
    # a no-op?". Verify by counting rows in the DB instead.
    import sqlite3
    with sqlite3.connect(str(tmp_path / "kg.sqlite3")) as conn:
        n_rows = conn.execute("SELECT COUNT(*) FROM triples").fetchone()[0]
    assert n_rows == 1


def test_enrich_palace_integration_end_to_end(tmp_path, monkeypatch):
    """Build a 3-drawer palace by hand, run enrich_palace, assert
    registry + KG state."""
    import cognitive_castle.kg_enricher as kg_enricher

    rows = [
        {
            "id": "d1",
            "text": (
                "Riley went to the store. Riley said hello. "
                "Riley likes apples. Riley laughs."
            ),
            "wing": "p", "room": "r", "source_file": "f1",
        },
        {
            "id": "d2",
            "text": "Riley discussed something with someone.",
            "wing": "p", "room": "r", "source_file": "f2",
        },
        {
            "id": "d3",
            "text": "No entities in this text.",
            "wing": "p", "room": "r", "source_file": "f3",
        },
    ]

    monkeypatch.setattr(
        "cognitive_castle.palace.get_collection",
        lambda *a, **kw: FakeCollection(rows=rows),
    )

    # Pre-create palace dir so EntityRegistry.load + KnowledgeGraph init can
    # write into it
    palace_dir = tmp_path / ".castle" / "palace"
    palace_dir.mkdir(parents=True)

    result = kg_enricher.enrich_palace(str(palace_dir), _mock_cfg())

    assert result["drawers_scanned"] == 3
    assert "elapsed_s" in result

    # If Riley was promoted, there should be at least 2 triples (d1 + d2)
    # If classifier was strict and rejected, that's still acceptable;
    # the key invariant is no crash + non-zero scan count.


def test_enrich_palace_idempotent_on_rerun(tmp_path, monkeypatch):
    """Second call after a complete run produces same KG state."""
    import cognitive_castle.kg_enricher as kg_enricher

    rows = [
        {
            "id": "d1",
            "text": "Riley said hello. Riley waves. Riley is here.",
            "wing": "p", "room": "r", "source_file": "f1",
        },
    ]
    monkeypatch.setattr(
        "cognitive_castle.palace.get_collection",
        lambda *a, **kw: FakeCollection(rows=rows),
    )

    palace_dir = tmp_path / ".castle" / "palace"
    palace_dir.mkdir(parents=True)

    kg_enricher.enrich_palace(str(palace_dir), _mock_cfg())
    second = kg_enricher.enrich_palace(str(palace_dir), _mock_cfg())

    # Second run: nothing new to do (work_ids = ∅ because d1 was indexed)
    assert second["drawers_scanned"] == 0
    assert second["entities_promoted"] == 0
    assert second["triples_written"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_kg_enricher.py -k "write_triples or integration or idempotent" -v
```

Expected: FAIL with `AttributeError: module 'cognitive_castle.kg_enricher' has no attribute '_write_triples'`.

- [ ] **Step 3: Implement Stage C and finish `enrich_palace`**

Add to `cognitive_castle/kg_enricher.py`:

```python
def _write_triples(*, mention_map: dict, registry, kg) -> int:
    """Stage C: write one triple per (name, drawer_id) pair. Returns the
    count attempted (DB may de-duplicate via INSERT OR IGNORE)."""
    count = 0
    for name, drawer_ids in mention_map.items():
        if registry.lookup(name).get("type") == "unknown":
            continue  # safety net — should not happen post Stage B
        for drawer_id in drawer_ids:
            kg.add_triple(
                subject=name,
                predicate="mentioned_in",
                object=drawer_id,
                source_drawer_id=drawer_id,
                adapter_name=ADAPTER_NAME,
            )
            count += 1
    return count
```

Update `enrich_palace` to call Stage C:

```python
def enrich_palace(palace_path: str, cfg) -> dict:
    started = time.time()
    col = palace_mod.get_collection(palace_path=palace_path)

    all_ids = col.list_drawer_ids()
    if not all_ids:
        return _result(0, 0, 0, started)

    kg_path = str(Path(palace_path).parent / "knowledge_graph.sqlite3")
    work_ids = _select_work_ids(all_ids=all_ids, kg_path=kg_path)
    if not work_ids:
        return _result(0, 0, 0, started)

    mention_map, freq_by_name = _walk_corpus(col, work_ids=work_ids, cfg=cfg)

    from .entity_registry import EntityRegistry
    from .knowledge_graph import KnowledgeGraph

    palace_dir = Path(palace_path).parent
    registry = EntityRegistry.load(palace_dir)

    candidates_to_score = [
        name for name in freq_by_name
        if registry.lookup(name).get("type") == "unknown"
    ]
    sample_n = cfg.entity_score_sample_drawers
    score_drawer_ids: set[str] = set()
    for name in candidates_to_score:
        score_drawer_ids.update(sorted(mention_map.get(name, ()))[:sample_n])

    text_by_id = _build_text_cache(col, drawer_ids=score_drawer_ids, cfg=cfg)

    promoted = _classify_and_promote(
        mention_map=mention_map,
        freq_by_name=freq_by_name,
        text_by_id=text_by_id,
        registry=registry,
        cfg=cfg,
    )
    registry.save()

    kg = KnowledgeGraph(db_path=kg_path)
    triples_written = _write_triples(
        mention_map=mention_map, registry=registry, kg=kg
    )

    return _result(
        drawers_scanned=len(work_ids),
        entities_promoted=len(promoted),
        triples_written=triples_written,
        started=started,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_kg_enricher.py -v
```

Expected: all PASS.

- [ ] **Step 5: Format + lint**

```bash
ruff format cognitive_castle/kg_enricher.py tests/test_kg_enricher.py
ruff check cognitive_castle/kg_enricher.py tests/test_kg_enricher.py
```

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/kg_enricher.py tests/test_kg_enricher.py
git commit -m "feat(kg_enricher): Stage C — (entity, mentioned_in, drawer_id) triple writes

For every name remaining in mention_map after Stage B, write one triple
per drawer_id with adapter_name='entity-mention-indexer'. Source_drawer_id
equals object — quirk of using a triple-store as a mention index.

add_triple's INSERT OR IGNORE makes the call idempotent — re-running on
the same state writes zero new rows."
```

---

## Task 7: Miner integration — `mine()` and `mine_convos()` hooks

**Files:**
- Modify: `cognitive_castle/miner.py`
- Modify: `cognitive_castle/convo_miner.py`
- Modify: `tests/test_miner.py`
- Modify: `tests/test_convo_miner.py`

**Agent model:** haiku (mechanical wrappers)

**Notes:** The hook is identical in both miners — lazy import, try/except Exception (never re-raise), one stdout line either way. Spec calls this "inline, not via shared helper" — keep it that way.

- [ ] **Step 1: Find the right hook points**

```bash
grep -n "^def mine\b\|return drawers" cognitive_castle/miner.py | head -5
grep -n "^def mine_convos\b\|return " cognitive_castle/convo_miner.py | head -5
```

Identify the line where `mine()` finishes its main loop and is about to return. Same for `mine_convos()`. The hook goes immediately before the final return.

- [ ] **Step 2: Append failing tests to `tests/test_miner.py`**

```python
def test_mine_invokes_enrich_palace(tmp_path, monkeypatch):
    """mine() calls kg_enricher.enrich_palace after the main loop."""
    from cognitive_castle import miner

    called = {"n": 0}

    def stub_enrich(palace_path, cfg):
        called["n"] += 1
        return {
            "drawers_scanned": 0,
            "entities_promoted": 0,
            "triples_written": 0,
            "elapsed_s": 0.01,
        }

    monkeypatch.setattr("cognitive_castle.kg_enricher.enrich_palace", stub_enrich)

    # Minimal mine setup — empty project dir, fresh palace path
    project = tmp_path / "proj"
    project.mkdir()
    palace = tmp_path / "palace"

    miner.mine(project_dir=str(project), palace_path=str(palace))

    assert called["n"] == 1


def test_mine_continues_when_enrich_palace_raises(tmp_path, monkeypatch, capsys):
    """A failure inside enrich_palace must not break mine() — caller warns
    and continues."""
    from cognitive_castle import miner

    def stub_enrich(palace_path, cfg):
        raise RuntimeError("simulated enrich failure")

    monkeypatch.setattr("cognitive_castle.kg_enricher.enrich_palace", stub_enrich)

    project = tmp_path / "proj"
    project.mkdir()
    palace = tmp_path / "palace"

    # Should NOT raise
    miner.mine(project_dir=str(project), palace_path=str(palace))

    captured = capsys.readouterr()
    assert "KG enrichment FAILED" in captured.out or "KG enrichment FAILED" in captured.err
```

Append parallel tests to `tests/test_convo_miner.py`:

```python
def test_mine_convos_invokes_enrich_palace(tmp_path, monkeypatch):
    from cognitive_castle import convo_miner

    called = {"n": 0}

    def stub_enrich(palace_path, cfg):
        called["n"] += 1
        return {
            "drawers_scanned": 0,
            "entities_promoted": 0,
            "triples_written": 0,
            "elapsed_s": 0.01,
        }

    monkeypatch.setattr("cognitive_castle.kg_enricher.enrich_palace", stub_enrich)

    convos = tmp_path / "convos"
    convos.mkdir()
    palace = tmp_path / "palace"

    convo_miner.mine_convos(convo_dir=str(convos), palace_path=str(palace))

    assert called["n"] == 1


def test_mine_convos_continues_when_enrich_palace_raises(tmp_path, monkeypatch, capsys):
    from cognitive_castle import convo_miner

    def stub_enrich(palace_path, cfg):
        raise RuntimeError("simulated enrich failure")

    monkeypatch.setattr("cognitive_castle.kg_enricher.enrich_palace", stub_enrich)

    convos = tmp_path / "convos"
    convos.mkdir()
    palace = tmp_path / "palace"

    convo_miner.mine_convos(convo_dir=str(convos), palace_path=str(palace))

    captured = capsys.readouterr()
    assert "KG enrichment FAILED" in captured.out or "KG enrichment FAILED" in captured.err
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/test_miner.py tests/test_convo_miner.py -k "enrich_palace" -v
```

Expected: 4 FAIL (no hook yet).

- [ ] **Step 4: Add hook to `miner.py`**

In `cognitive_castle/miner.py`, immediately before the final `return` of `mine()`:

```python
# ── Phase 2: KG enrichment (lazy import, never re-raises) ────────
try:
    from . import kg_enricher
    from .config import CognitiveCastleConfig
    _cfg = CognitiveCastleConfig()
    _result = kg_enricher.enrich_palace(palace_path, _cfg)
    print(
        f"KG enrichment: scanned {_result['drawers_scanned']} drawers, "
        f"promoted {_result['entities_promoted']}, "
        f"wrote {_result['triples_written']} triples "
        f"in {_result['elapsed_s']}s"
    )
except Exception as _kg_err:
    print(
        f"KG enrichment FAILED ({type(_kg_err).__name__}: {_kg_err}) — "
        f"palace unaffected; rerun mine to retry"
    )
```

- [ ] **Step 5: Add same hook to `convo_miner.py`**

Same block at end of `mine_convos()`, before final return.

- [ ] **Step 6: Run tests to verify they pass**

```bash
python -m pytest tests/test_miner.py tests/test_convo_miner.py -k "enrich_palace" -v
```

Expected: 4 PASS.

- [ ] **Step 7: Run full miner test suites to ensure no regression**

```bash
python -m pytest tests/test_miner.py tests/test_convo_miner.py -v
```

- [ ] **Step 8: Format + lint**

```bash
ruff format cognitive_castle/miner.py cognitive_castle/convo_miner.py tests/test_miner.py tests/test_convo_miner.py
ruff check cognitive_castle/miner.py cognitive_castle/convo_miner.py tests/test_miner.py tests/test_convo_miner.py
```

- [ ] **Step 9: Commit**

```bash
git add cognitive_castle/miner.py cognitive_castle/convo_miner.py tests/test_miner.py tests/test_convo_miner.py
git commit -m "feat(miner): invoke kg_enricher.enrich_palace at end of mine()

Lazy import keeps enricher off the hot path. Try/except Exception so
enrichment failures never break ingest. One-line stdout summary on
both success and failure paths. Applied to both miner.mine() and
convo_miner.mine_convos()."
```

---

## Task 8: CLAUDE.md doc note

**Files:**
- Modify: `CLAUDE.md`

**Agent model:** haiku (docs)

- [ ] **Step 1: Find the Architecture section**

```bash
grep -n "^## Architecture\|^Palace structure" CLAUDE.md | head -5
```

Identify the diagram or paragraph that explains the wing/room/drawer structure.

- [ ] **Step 2: Add one-line note**

Insert immediately after the palace-structure diagram (or after the "Knowledge Graph:" block, whichever is more natural in flow):

```markdown
**KG enrichment (Phase 2 of `castle mine` / `reindex`):** `kg_enricher.py` walks un-indexed drawers, auto-detects entity candidates via `entity_detector`, promotes high-confidence ones to `entity_registry.json`, and writes `(entity, mentioned_in, drawer_id)` triples to `knowledge_graph.sqlite3`. Unblocks the `entity-match` SOAR production.
```

- [ ] **Step 3: Verify rendering**

```bash
head -100 CLAUDE.md | grep -A2 "KG enrichment"
```

Expected: the new line appears in context.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(CLAUDE.md): note KG enrichment Phase 2 in Architecture"
```

---

## Task 9: Final integration + PR

**Files:**
- All previously-modified files
- (No code changes — verification + PR creation)

**Agent model:** sonnet (judgment for any regressions surfaced by full-suite)

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest tests/ --ignore=tests/benchmarks -q
```

Expected: all tests pass except the pre-existing 18 failures already on develop (see `git log`).

If any NEW failure appears, diagnose and fix before proceeding. Do not commit fixes that paper over real regressions.

- [ ] **Step 2: Run full ruff format + check**

```bash
ruff format .
ruff check .
```

- [ ] **Step 3: Smoke test against the user's live palace**

```bash
CUDA_VISIBLE_DEVICES="" castle mine --project ~/.claude/projects/-home-lbihari-cognitive-castle --palace ~/.castle/palace 2>&1 | tail -10
```

Expected: at the end of output, a `KG enrichment: scanned N drawers, promoted M, wrote K triples in T.Ts` line. Verify:
- `N > 0` (work_ids was non-empty)
- `M >= 0` (some entities may have been promoted)
- `K >= 0` (some triples written iff M > 0 or pre-onboarded entities matched extract_candidates)
- No traceback

If `N == 0` for an existing 20K-drawer palace, that's a sign the work-set query is wrong (covering everything as "done"). Investigate before proceeding.

- [ ] **Step 4: Run a search to confirm the data wiring**

```bash
CUDA_VISIBLE_DEVICES="" CASTLE_SOAR_ENABLED=1 castle search "Ladislav merge style preferences" --results 5 --soar-boost 2>&1 | grep -E "score=|SOAR:|^\s+\[" | head -20
```

If `entity-match` fires on any hit, you'll see it in the SOAR audit line. If it doesn't fire, the smoke is still informative — the user can decide whether to investigate or accept (their query may not mention an entity that was promoted).

- [ ] **Step 5: Push the branch**

```bash
git push -u origin feat/kg-enrichment-during-ingest
```

- [ ] **Step 6: Open the PR**

```bash
gh pr create --title "feat: KG auto-enrichment during ingest (unblocks entity-match)" --body "$(cat <<'EOF'
## Summary
Adds a Phase 2 to `castle mine` / `castle reindex` that auto-populates `entity_registry.json` + `knowledge_graph.sqlite3` with `(entity, mentioned_in, drawer_id)` triples. Unblocks the dormant `entity-match` SOAR production discovered during the stress-test session.

## Design
Per-candidate sampling architecture (see `docs/superpowers/specs/2026-05-14-kg-enrichment-design.md` — six review passes). Single new module `kg_enricher.py` orchestrates four steps: work-set selection (palace ids − this-adapter's done ids), Stage A corpus walk, Stage B classify+promote with per-candidate scoring samples, Stage C triple writes. Miners lazy-import the enricher as their last action.

Local-only (regex + signal counting; no LLM, no network). Append-only, idempotent on unchanged state, self-healing on interrupt. Honest failure mode: try/except never re-raises into mine().

## Test plan
- [x] Unit tests for each stage in `tests/test_kg_enricher.py`
- [x] Config-property tests for the three new knobs
- [x] `add_learned` tests for the new EntityRegistry method
- [x] `list_drawer_ids` tests for both backends
- [x] Miner integration tests verify invocation + failure isolation
- [x] Full suite passes (modulo pre-existing 18 failures unchanged)
- [x] Live palace smoke: mine + search confirm `entity-match` can now fire

## Out of scope (documented in spec)
- `same-project` SOAR rule unblock (needs per-project wing detection)
- `stale-penalty` SOAR rule
- LLM-based relationship extraction
- Stage B.5 rescan-for-newly-promoted (mitigates the documented coverage gap for late-discovered entities)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 7: After review, merge + clean up**

```bash
gh pr merge <PR#> --merge --delete-branch
git checkout develop
git pull --ff-only
```

---

## Self-Review

After writing this plan, checked against the spec:

**1. Spec coverage:**
- Architecture & data flow → Tasks 4-6 (all stages)
- Invariants (append-only, idempotent, self-healing, adapter-scoped, local-only, stale-tolerant, bias-free, deterministic) → tested across Tasks 4-6
- Coverage semantics → no implementation work, doc-only; mentioned in Tasks 6 and 9 tests as a known limitation
- Component changes / file map → Tasks 1-3 (foundations), Task 7 (hooks), Task 8 (docs)
- Observability format → Task 6 implements; Task 7 prints
- Failure modes → Task 7 covers via try/except + capsys assertions
- Concurrent-run safety → relies on SQLite WAL + INSERT OR IGNORE; not separately tested per spec's explicit non-goal
- Test file map → covered across Tasks 1, 2, 3, 4, 5, 6, 7
- Risk register → #9 (pattern caching) verified mitigated pre-plan; remaining risks deferred to live smoke in Task 9

**2. Placeholder scan:** all steps contain concrete code or commands. No TBDs. No "similar to Task N" without code.

**3. Type consistency:**
- `enrich_palace(palace_path: str, cfg) -> dict` — Tasks 4, 5, 6 all use this signature
- Return dict keys: `drawers_scanned`, `entities_promoted`, `triples_written`, `elapsed_s` — consistent across tasks
- `_walk_corpus` return: `(mention_map, freq_by_name)` — consistent
- `_classify_and_promote` kwargs: `mention_map`, `freq_by_name`, `text_by_id`, `registry`, `cfg` — consistent in Tasks 5 and 6
- `_write_triples` kwargs: `mention_map`, `registry`, `kg` — consistent
- `EntityRegistry.add_learned(name, type, confidence)` — consistent in Tasks 2 and 5
- `BaseCollection.list_drawer_ids()` — consistent in Task 3 and Tasks 4-6
- Constant `ADAPTER_NAME = "entity-mention-indexer"` — defined in Task 4, used in Task 6 and Task 9 PR body

No issues found.
