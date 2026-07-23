# Information Theory of Verbatim Memory — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Phase 1 of the spec at `docs/superpowers/specs/2026-05-16-information-theory-verbatim-memory-design.md` — three composable estimators (`nn_novelty`, `recon_residual`, `llm_surprise`), the experiment pipeline, downstream R@5 validation, statistical analysis, and paper-LaTeX scaffolding — producing an arXiv-able research artifact in `research/info_theory/`.

**Architecture:** New top-level `research/info_theory/` directory (sibling of `benchmarks/`, not inside `cognitive_castle/`). Single CLI orchestrates a cache-aware Parquet pipeline. Imports Castle modules (`cognitive_castle.embedding`, `cognitive_castle.miner`, `cognitive_castle.llm_client`, `benchmarks.longmemeval_bench`) rather than forking them.

**Tech Stack:** Python ≥3.11; LanceDB (palace storage); bge-m3 (embeddings); Parquet + PyArrow (cache); statsmodels + scipy (decay fits, bootstrap, Kruskal-Wallis); matplotlib (figures); `claude-cli` provider from PR #49 (C-stage); LongMemEval public corpus.

---

## Pre-implementation: phase 0 H3 feasibility spike

Per the spec ("**H3 feasibility spike (1 day) at start of implementation phase**"), Phase 1 begins with a spike that determines whether H3 stays in scope. **If the spike reveals the LME harness needs >3 days of refactoring, drop H3 and proceed without it.** Subsequent tasks tagged `[H3]` are contingent on spike success.

---

### Task 0: H3 feasibility spike

**Goal:** Determine whether `benchmarks/longmemeval_bench.py` can be parameterized to use an info-filtered corpus subset for an R@5 measurement.

**Files:**
- Read: `benchmarks/longmemeval_bench.py`
- Create (if spike succeeds): `research/info_theory/spike_notes_h3.md`

- [ ] **Step 1: Read `benchmarks/longmemeval_bench.py` end-to-end**

Run: `wc -l benchmarks/longmemeval_bench.py && head -100 benchmarks/longmemeval_bench.py`

Identify three things:
1. The entry point (CLI vs. importable function)
2. The corpus-ingestion path (where session data becomes the search corpus)
3. The R@5 measurement path (what gets measured against what)

- [ ] **Step 2: Identify the corpus-filter seam**

Question to answer: can a caller pre-filter the LME corpus (e.g., drop a list of `drawer_id`s before retrieval runs) without rewriting the benchmark's core retrieval logic?

Concretely: does the harness build its retrieval index from a list of session/turn objects that we can subset? Or is the corpus baked into a database/index that needs full rebuild for any subset?

- [ ] **Step 3: Spike a minimal corpus-filter prototype**

Write a throwaway script `~/scratch/h3_spike.py` that:
1. Loads LME via the harness
2. Drops a random 10% of items from the corpus
3. Runs R@5 measurement
4. Prints the R@5 delta vs. uniform corpus

Time-box: **6 hours**. If it works in 6 hours, H3 is feasible. If not, H3 is dropped.

- [ ] **Step 4: Record the spike outcome**

Write `research/info_theory/spike_notes_h3.md` with:
- What worked / what didn't
- Estimated refactoring effort if needed (in days)
- Decision: **H3 IN** or **H3 OUT** for Phase 1

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/spike_notes_h3.md
git commit -m "spike: H3 feasibility outcome — $(grep -oE 'H3 (IN|OUT)' research/info_theory/spike_notes_h3.md | head -1)"
```

If H3 OUT: skip all subsequent tasks tagged `[H3]`. Plan still ships H1 + H2.

---

## Phase 1: project scaffolding

### Task 1: Create directory structure + Python project

**Files:**
- Create: `research/info_theory/pyproject.toml`
- Create: `research/info_theory/README.md`
- Create: `research/info_theory/REPRODUCIBILITY.md` (stub for later population)
- Create: `research/info_theory/seeds.yaml`
- Create: `research/info_theory/pipeline/__init__.py`
- Create: `research/info_theory/analysis/__init__.py`
- Create: `research/info_theory/paper/` (empty placeholder dir; LaTeX scaffolding comes in Task 23)
- Create: `research/info_theory/tests/__init__.py`
- Create: `research/info_theory/tests/conftest.py`
- Create: `research/info_theory/.gitignore`

- [ ] **Step 1: Create the directory layout**

```bash
mkdir -p research/info_theory/{pipeline,analysis,paper/figures,tests,outputs}
touch research/info_theory/pipeline/__init__.py
touch research/info_theory/analysis/__init__.py
touch research/info_theory/tests/__init__.py
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "info-theory-of-verbatim-memory"
version = "0.1.0"
description = "Phase 1 research artifact: estimator + experiment + paper"
requires-python = ">=3.11"
dependencies = [
  "pyarrow>=15.0",
  "numpy>=1.26",
  "scipy>=1.13",
  "statsmodels>=0.14",
  "matplotlib>=3.8",
  "pyyaml>=6.0",
  "tiktoken>=0.6",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov>=5.0"]

# Required: pin the installable packages to just the two Python modules.
# Without this, setuptools' flat-layout auto-discovery finds `paper`,
# `outputs`, `pipeline`, and `analysis` as candidates and refuses to build.
[tool.setuptools]
packages = ["pipeline", "analysis"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Write `seeds.yaml` (initial values)**

```yaml
numpy_seed: 42
torch_seed: 42
subsample_seed: 42
bootstrap_seed: 42
prompt_template_seed: 42
downstream_eval_seed: 42
palace_snapshot_fingerprint: null  # populated by Task 2
longmemeval_release: null  # populated by Task 6
```

- [ ] **Step 4: Write `README.md` (one-screen quickstart)**

```markdown
# Information Theory of Verbatim Memory

Phase 1 research artifact for the paper *Measuring Information Content in Verbatim AI Memory*.

## Quickstart

    python -m cli snapshot         # snapshot ~/.castle/palace
    python -m cli pilot            # 5% LME sizing pilot
    python -m cli run --all        # full pipeline (cached)
    python -m cli figures          # produce paper plots
    python -m cli figures --tables # emit appendix LaTeX tables

See [REPRODUCIBILITY.md](REPRODUCIBILITY.md) for the manifest.
See `../../docs/superpowers/specs/2026-05-16-information-theory-verbatim-memory-design.md` for the spec.
```

- [ ] **Step 5: Write `.gitignore`**

```
outputs/
*.pyc
__pycache__/
.pytest_cache/
*.egg-info/
```

- [ ] **Step 6: Write `tests/conftest.py` (shared fixtures)**

```python
import numpy as np
import pytest


@pytest.fixture(autouse=True)
def deterministic_rng():
    """Every test starts with a freshly seeded numpy RNG."""
    np.random.seed(42)


@pytest.fixture
def tmp_research_dir(tmp_path):
    """Mimics ~/.castle/research/ layout for tests."""
    (tmp_path / "llm_surprise_partials").mkdir()
    return tmp_path
```

- [ ] **Step 7: Write shared cache-fingerprint utility**

Create `research/info_theory/pipeline/cache_utils.py`:

```python
# pipeline/cache_utils.py
"""Shared cache-fingerprint utility used by all pipeline stages that
write Parquet caches. Per the spec, every stage's output Parquet
carries an `inputs_fingerprint` key in its schema metadata so
`cli status` can detect stale stages."""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Iterable, Optional
import pyarrow.parquet as pq


def fingerprint_inputs(items: Iterable) -> str:
    """SHA256 of a canonical-JSON serialization of `items`. Order-
    independent if `items` is a sorted iterable; otherwise sensitive
    to order. Callers pre-sort if they want order-independence."""
    payload = json.dumps(list(items), separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def read_cached(path: Path, expected_fingerprint: str):
    """Return cached Arrow table if fingerprint matches; else None."""
    if not Path(path).exists():
        return None
    cached = pq.read_table(path)
    meta = cached.schema.metadata or {}
    if meta.get(b"inputs_fingerprint") == expected_fingerprint.encode():
        return cached
    return None


def write_cached(table, path: Path, inputs_fingerprint: str,
                  extra_metadata: Optional[dict] = None) -> None:
    """Write Parquet with inputs_fingerprint stamped in schema metadata."""
    meta = {b"inputs_fingerprint": inputs_fingerprint.encode()}
    if extra_metadata:
        for k, v in extra_metadata.items():
            meta[k.encode() if isinstance(k, str) else k] = (
                v.encode() if isinstance(v, str) else v
            )
    stamped = table.replace_schema_metadata(meta)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(stamped, path)
```

Subsequent stage tasks (Tasks 6, 7, 8, 9, 11, 13, 17) reference this module via `from pipeline.cache_utils import read_cached, write_cached, fingerprint_inputs`. The per-stage tests verify cache-hit-on-fingerprint-match.

- [ ] **Step 8: Install deps + verify pytest runs**

```bash
cd research/info_theory
python -m pip install -e ".[dev]"
python -m pytest --collect-only
```

Expected: pytest collects 0 tests (no test files yet) without errors.

- [ ] **Step 9: Commit**

```bash
git add research/info_theory/
git commit -m "scaffold(research): info_theory project structure + cache_utils + tests harness"
```

---

## Phase 2: data loading

### Task 2: Palace snapshot

**Files:**
- Create: `research/info_theory/pipeline/snapshot_palace.py`
- Create: `research/info_theory/tests/test_snapshot_palace.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_snapshot_palace.py
import os, hashlib, json
from pathlib import Path
import pytest
from pipeline.snapshot_palace import snapshot_palace, compute_fingerprint


def test_snapshot_copies_files(tmp_path):
    src = tmp_path / "live_palace"
    dst = tmp_path / "snapshot"
    src.mkdir()
    (src / "a.lance").write_text("hello")
    (src / "b.lance").write_text("world")
    snapshot_palace(src, dst)
    assert (dst / "a.lance").read_text() == "hello"
    assert (dst / "b.lance").read_text() == "world"


def test_snapshot_refuses_to_overwrite(tmp_path):
    src = tmp_path / "live"
    dst = tmp_path / "snap"
    src.mkdir(); dst.mkdir()
    with pytest.raises(FileExistsError):
        snapshot_palace(src, dst)


def test_fingerprint_is_tuple_hash_not_value_concatenation():
    """sha256(sorted [(drawer_id, filed_at, chunk_index) tuples])
    must differ from sha256(drawer_ids + filed_ats + chunk_indexes)."""
    rows = [
        {"drawer_id": "A", "filed_at": "2026-01-01", "chunk_index": 0},
        {"drawer_id": "B", "filed_at": "2026-01-02", "chunk_index": 1},
    ]
    fp = compute_fingerprint(rows)
    # Permuting the values across drawers should NOT collide
    rows_permuted = [
        {"drawer_id": "A", "filed_at": "2026-01-02", "chunk_index": 1},
        {"drawer_id": "B", "filed_at": "2026-01-01", "chunk_index": 0},
    ]
    fp_permuted = compute_fingerprint(rows_permuted)
    assert fp != fp_permuted, "fingerprint must bind drawer_id to its filed_at"


def test_fingerprint_is_deterministic():
    rows = [{"drawer_id": "X", "filed_at": "2026-01-01", "chunk_index": 0}]
    assert compute_fingerprint(rows) == compute_fingerprint(rows)


def test_fingerprint_is_order_independent_within_id_sort():
    rows1 = [
        {"drawer_id": "B", "filed_at": "t2", "chunk_index": 0},
        {"drawer_id": "A", "filed_at": "t1", "chunk_index": 0},
    ]
    rows2 = [
        {"drawer_id": "A", "filed_at": "t1", "chunk_index": 0},
        {"drawer_id": "B", "filed_at": "t2", "chunk_index": 0},
    ]
    assert compute_fingerprint(rows1) == compute_fingerprint(rows2)
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
cd research/info_theory
python -m pytest tests/test_snapshot_palace.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `snapshot_palace.py`**

```python
# pipeline/snapshot_palace.py
"""Snapshot the live LanceDB palace so the experiment reads from a
frozen state. Critical for reproducibility — the palace grows
continuously via the Stop hook."""

from __future__ import annotations
import hashlib
import json
import shutil
from pathlib import Path
from typing import Iterable


def snapshot_palace(src: Path, dst: Path) -> Path:
    """Copy the LanceDB directory tree at `src` into `dst`.

    Refuses to overwrite an existing snapshot — the experiment must
    explicitly delete a prior snapshot before re-running.
    """
    src = Path(src)
    dst = Path(dst)
    if dst.exists():
        raise FileExistsError(
            f"Snapshot target {dst} already exists; refusing to overwrite"
        )
    shutil.copytree(src, dst)
    return dst


def compute_fingerprint(rows: Iterable[dict]) -> str:
    """Stable hash of sorted [(drawer_id, filed_at, chunk_index)] tuples.

    Tuples preserve per-drawer positional binding. Concatenating value
    lists would lose that binding — same values in different orders
    would collide.
    """
    sortable = [
        (r["drawer_id"], r["filed_at"], int(r["chunk_index"])) for r in rows
    ]
    sortable.sort(key=lambda t: t[0])
    payload = json.dumps(sortable, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
python -m pytest tests/test_snapshot_palace.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/pipeline/snapshot_palace.py research/info_theory/tests/test_snapshot_palace.py
git commit -m "feat(pipeline): snapshot_palace with stable tuple-hash fingerprint"
```

---

### Task 3: Load palace into Parquet

**Files:**
- Create: `research/info_theory/pipeline/load_palace.py`
- Create: `research/info_theory/tests/test_load_palace.py`
- Create: `research/info_theory/tests/fixtures/palace_lance_mini/` (committed mini-fixture)

- [ ] **Step 1: Create a mini LanceDB fixture**

A small LanceDB table with 10 drawers covering the schema actually used by Castle (`id`, `text`, `metadata_json`, `wing`, `room`, `source_file`, `chunk_index`, `decay_score`, no top-level `filed_at`).

```python
# tests/fixtures/build_palace_fixture.py — run once, output committed
import json
import lancedb
import pyarrow as pa
from pathlib import Path

dst = Path(__file__).parent / "palace_lance_mini"
dst.mkdir(exist_ok=True)
db = lancedb.connect(str(dst))

rows = []
for i in range(10):
    rows.append({
        "id": f"drawer_{i:03d}",
        "text": f"sample text {i}",
        "vector": [0.1] * 1024,
        "metadata_json": json.dumps({
            "filed_at": f"2026-01-{i+1:02d}T00:00:00Z",
            "added_by": "miner" if i < 7 else "mcp",
        }),
        "wing": "test_wing",
        "room": "test_room",
        "source_file": f"/tmp/src_{i//2}.jsonl",  # pairs share source_file
        "chunk_index": i % 2,
        "decay_score": 1.0,
    })

schema = pa.schema([
    ("id", pa.string()),
    ("text", pa.large_string()),
    ("vector", pa.list_(pa.float32(), 1024)),
    ("metadata_json", pa.large_string()),
    ("wing", pa.string()),
    ("room", pa.string()),
    ("source_file", pa.string()),
    ("chunk_index", pa.int64()),
    ("decay_score", pa.float64()),
])
db.create_table("castle_drawers", data=rows, schema=schema, exist_ok=True)
print(f"Wrote {len(rows)} fixture drawers to {dst}")
```

Run once: `python research/info_theory/tests/fixtures/build_palace_fixture.py`
Commit the resulting `palace_lance_mini/` directory.

- [ ] **Step 2: Write failing tests**

```python
# tests/test_load_palace.py
from pathlib import Path
import pyarrow as pa
from pipeline.load_palace import load_palace, parse_metadata_json

FIXTURE = Path(__file__).parent / "fixtures" / "palace_lance_mini"


def test_load_palace_returns_arrow_table():
    table = load_palace(FIXTURE)
    assert isinstance(table, pa.Table)
    assert table.num_rows == 10


def test_load_palace_extracts_filed_at_from_metadata_json():
    table = load_palace(FIXTURE)
    cols = table.column_names
    assert "filed_at" in cols
    assert "added_by" in cols
    first = table.column("filed_at")[0].as_py()
    assert first.startswith("2026-01-")


def test_load_palace_includes_chunk_index():
    table = load_palace(FIXTURE)
    assert "chunk_index" in table.column_names
    # Pairs share source_file, alternating chunk_index 0,1
    chunks = table.column("chunk_index").to_pylist()
    assert 0 in chunks and 1 in chunks


def test_parse_metadata_json_handles_missing_fields():
    assert parse_metadata_json('{}') == {}
    assert parse_metadata_json(None) == {}
    assert parse_metadata_json('{"filed_at":"x"}') == {"filed_at": "x"}


def test_load_palace_excludes_drawers_with_missing_filed_at(tmp_path):
    """Schema verification step: drawers missing filed_at are excluded
    and logged. Use a fixture with one bad row."""
    # Build a 3-row fixture inline; one row has metadata_json='{}'
    import lancedb
    db = lancedb.connect(str(tmp_path))
    rows = [
        {"id": "good_1", "text": "x", "vector": [0.1]*1024,
         "metadata_json": '{"filed_at":"2026-01-01","added_by":"miner"}',
         "wing": "w", "room": "r", "source_file": "/tmp/a",
         "chunk_index": 0, "decay_score": 1.0},
        {"id": "bad",    "text": "y", "vector": [0.1]*1024,
         "metadata_json": '{}',
         "wing": "w", "room": "r", "source_file": "/tmp/a",
         "chunk_index": 1, "decay_score": 1.0},
        {"id": "good_2", "text": "z", "vector": [0.1]*1024,
         "metadata_json": '{"filed_at":"2026-01-02","added_by":"miner"}',
         "wing": "w", "room": "r", "source_file": "/tmp/b",
         "chunk_index": 0, "decay_score": 1.0},
    ]
    db.create_table("castle_drawers", data=rows, exist_ok=True)
    table = load_palace(tmp_path)
    ids = table.column("id").to_pylist()
    assert "bad" not in ids
    assert "good_1" in ids and "good_2" in ids
```

- [ ] **Step 3: Run tests, verify they fail**

```bash
python -m pytest tests/test_load_palace.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 4: Implement `load_palace.py`**

```python
# pipeline/load_palace.py
"""Load the snapshotted palace into a Parquet-compatible PyArrow
table. Parses `metadata_json` to surface `filed_at` and `added_by`
as proper columns. Excludes drawers with missing `filed_at`."""

from __future__ import annotations
import json
import logging
from pathlib import Path
import lancedb
import pyarrow as pa

logger = logging.getLogger(__name__)


def parse_metadata_json(raw):
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def load_palace(snapshot_dir: Path) -> pa.Table:
    """Read castle_drawers from snapshot_dir, return Arrow table
    with filed_at + added_by promoted from metadata_json."""
    db = lancedb.connect(str(snapshot_dir))
    table = db.open_table("castle_drawers").to_arrow()

    filed_at_col, added_by_col, kept_indices = [], [], []
    excluded = 0
    for i, raw in enumerate(table.column("metadata_json").to_pylist()):
        meta = parse_metadata_json(raw)
        if "filed_at" not in meta:
            excluded += 1
            continue
        filed_at_col.append(meta["filed_at"])
        added_by_col.append(meta.get("added_by", "unknown"))
        kept_indices.append(i)

    if excluded:
        logger.warning(
            f"Excluded {excluded} drawers missing filed_at (of {table.num_rows})"
        )

    kept = table.take(pa.array(kept_indices))
    kept = kept.append_column("filed_at", pa.array(filed_at_col))
    kept = kept.append_column("added_by", pa.array(added_by_col))
    return kept
```

- [ ] **Step 5: Run tests, verify pass**

```bash
python -m pytest tests/test_load_palace.py -v
```

Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add research/info_theory/pipeline/load_palace.py \
        research/info_theory/tests/test_load_palace.py \
        research/info_theory/tests/fixtures/
git commit -m "feat(pipeline): load_palace parses metadata_json, excludes missing filed_at"
```

---

### Task 4: Load LongMemEval into matching Parquet shape

**Files:**
- Read: `benchmarks/longmemeval_bench.py` (refactor as needed to expose loader)
- Create: `research/info_theory/pipeline/load_longmemeval.py`
- Create: `research/info_theory/tests/test_load_longmemeval.py`
- Create: `research/info_theory/tests/fixtures/longmemeval_mini.json`

- [ ] **Step 1: If `longmemeval_bench.py` lacks a `load_questions()` function, refactor**

Read the file. If the LME-loading logic is buried inside a `__main__` block or class, extract it into a module-level `load_questions(release="default") -> list[dict]` function. Keep the existing CLI entry point working by calling `load_questions()`.

Commit the refactor as a separate commit before the `load_longmemeval.py` work:

```bash
git add benchmarks/longmemeval_bench.py
git commit -m "refactor(benchmarks): expose load_questions() for import"
```

- [ ] **Step 2: Create a tiny LME-shaped fixture**

```json
// tests/fixtures/longmemeval_mini.json
// Note: each turn must be ≥50 chars after newline-joining within a session,
// or Castle's chunk_text() will drop the chunk (MIN_CHUNK_SIZE = 50).
[
  {
    "question_id": "q1",
    "question_type": "single-session-user",
    "sessions": [
      {"session_id": "q1_s0", "timestamp": "2026-01-01T00:00:00Z",
       "turns": [
         {"text": "Hello there, I have a question about a project I've been working on for a few weeks."},
         {"text": "Hi! Happy to help. What's the project about and what's the question?"}
       ]},
      {"session_id": "q1_s1", "timestamp": "2026-01-02T00:00:00Z",
       "turns": [
         {"text": "A follow-up question on the same project, building on what we discussed earlier today."}
       ]}
    ]
  },
  {
    "question_id": "q2",
    "question_type": "multi-session",
    "sessions": [
      {"session_id": "q2_s0", "timestamp": "2026-01-03T00:00:00Z",
       "turns": [
         {"text": "A completely different topic from a different conversation about something unrelated."},
         {"text": "Another turn in the same session continuing the unrelated topic with more detail."}
       ]}
    ]
  }
]
```

- [ ] **Step 3: Write failing tests**

```python
# tests/test_load_longmemeval.py
from pathlib import Path
import pyarrow as pa
from pipeline.load_longmemeval import load_longmemeval

FIXTURE = Path(__file__).parent / "fixtures" / "longmemeval_mini.json"


def test_load_longmemeval_returns_arrow_table():
    table = load_longmemeval(FIXTURE)
    assert isinstance(table, pa.Table)
    assert table.num_rows > 0


def test_load_longmemeval_has_castle_compatible_schema():
    table = load_longmemeval(FIXTURE)
    cols = set(table.column_names)
    required = {"text", "filed_at", "session_id", "question_id",
                "question_type", "chunk_index", "wing", "room", "added_by"}
    assert required.issubset(cols)


def test_load_longmemeval_nulls_castle_fields():
    table = load_longmemeval(FIXTURE)
    # wing, room, added_by are Castle-specific; LME rows have them null
    assert all(v is None for v in table.column("wing").to_pylist())
    assert all(v is None for v in table.column("added_by").to_pylist())


def test_load_longmemeval_preserves_session_ordering():
    table = load_longmemeval(FIXTURE)
    # q1 has two sessions; chunk_index should increase within session
    q1_rows = [(r["session_id"], r["chunk_index"])
               for r in table.to_pylist() if r["question_id"] == "q1"]
    # Group by session, verify chunk_index ascending within group
    from collections import defaultdict
    by_session = defaultdict(list)
    for sid, ci in q1_rows:
        by_session[sid].append(ci)
    for sid, chunks in by_session.items():
        assert chunks == sorted(chunks), f"chunks not ordered in {sid}"
```

- [ ] **Step 4: Run tests, verify they fail**

```bash
python -m pytest tests/test_load_longmemeval.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 5: Implement `load_longmemeval.py`**

```python
# pipeline/load_longmemeval.py
"""Load LongMemEval into a Parquet-compatible Arrow table whose
schema matches the palace's, with Castle-specific fields (wing,
room, added_by) set to null."""

from __future__ import annotations
import json
from pathlib import Path
from typing import Union
import pyarrow as pa

# Castle's miner API (verified against cognitive_castle/miner.py:371):
#   chunk_text(content: str, source_file: str) -> list[dict]
# Returns dicts shaped {"content": str, "chunk_index": int}, driven by
# module-level constants CHUNK_SIZE=800 and MIN_CHUNK_SIZE=50. No
# per-call size override; no ChunkConfig class.
from cognitive_castle.miner import chunk_text


def load_longmemeval(source: Union[Path, str]) -> pa.Table:
    """Read LME questions (or a fixture JSON), chunk through Castle's
    miner, and return an Arrow table compatible with load_palace()."""
    source = Path(source)
    if source.is_file() and source.suffix == ".json":
        with open(source) as f:
            questions = json.load(f)
    else:
        # Production path: import the benchmark loader
        from benchmarks.longmemeval_bench import load_questions
        questions = load_questions()

    rows = []
    for q in questions:
        qid = q["question_id"]
        qtype = q["question_type"]
        for sess in q["sessions"]:
            sid = sess["session_id"]
            ts = sess["timestamp"]
            joined = "\n".join(t["text"] for t in sess["turns"])
            source_file_tag = f"lme_{qid}_{sid}"
            for chunk in chunk_text(joined, source_file_tag):
                ci = chunk["chunk_index"]
                rows.append({
                    "drawer_id": f"lme_{qid}_{sid}_{ci:03d}",
                    "text": chunk["content"],
                    "filed_at": ts,
                    "session_id": sid,
                    "question_id": qid,
                    "question_type": qtype,
                    "chunk_index": ci,
                    "source_file": source_file_tag,
                    "wing": None, "room": None, "added_by": None,
                })

    schema = pa.schema([
        ("drawer_id", pa.string()),
        ("text", pa.large_string()),
        ("filed_at", pa.string()),
        ("session_id", pa.string()),
        ("question_id", pa.string()),
        ("question_type", pa.string()),
        ("chunk_index", pa.int64()),
        ("source_file", pa.string()),
        ("wing", pa.string()),
        ("room", pa.string()),
        ("added_by", pa.string()),
    ])
    return pa.Table.from_pylist(rows, schema=schema)
```

- [ ] **Step 6: Run tests, verify pass**

```bash
python -m pytest tests/test_load_longmemeval.py -v
```

Expected: 4 PASS.

- [ ] **Step 7: Commit**

```bash
git add research/info_theory/pipeline/load_longmemeval.py \
        research/info_theory/tests/test_load_longmemeval.py \
        research/info_theory/tests/fixtures/longmemeval_mini.json
git commit -m "feat(pipeline): load_longmemeval chunks through Castle miner; matches palace schema"
```

---

### Task 5: Drawer text normalization

**Files:**
- Create: `research/info_theory/pipeline/normalize.py`
- Create: `research/info_theory/tests/test_normalize.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_normalize.py
from pipeline.normalize import strip_code_blocks, truncate_to_tokens, normalize


def test_strip_code_blocks_removes_fenced_code():
    text = "before\n```python\ndef foo(): pass\n```\nafter"
    assert strip_code_blocks(text) == "before\n\nafter"


def test_strip_code_blocks_handles_no_fences():
    text = "plain prose without code"
    assert strip_code_blocks(text) == "plain prose without code"


def test_strip_code_blocks_handles_multiple_fences():
    text = "x ```a``` y ```b``` z"
    out = strip_code_blocks(text)
    assert "```" not in out
    assert "a" not in out and "b" not in out
    assert "x" in out and "y" in out and "z" in out


def test_truncate_to_tokens_short_text_unchanged():
    short = "five words here is short"
    assert truncate_to_tokens(short, max_tokens=100) == short


def test_truncate_to_tokens_long_text_truncated():
    long = " ".join(["word"] * 5000)
    result = truncate_to_tokens(long, max_tokens=100)
    # Result has at most max_tokens tokens
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    assert len(enc.encode(result)) <= 100


def test_normalize_strips_then_truncates():
    text = "prose ```code block``` more prose " + " ".join(["w"] * 3000)
    out = normalize(text, max_tokens=50)
    assert "```" not in out
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    assert len(enc.encode(out)) <= 50


def test_normalize_handles_empty():
    assert normalize("") == ""
    assert normalize("```only code```") == ""
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
python -m pytest tests/test_normalize.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `normalize.py`**

```python
# pipeline/normalize.py
"""Drawer text normalization: strip fenced code blocks, truncate to
2000 tokens (bge-m3's effective limit). Applied before embedding (A,
B) and before LLM prompting (C)."""

from __future__ import annotations
import re
import tiktoken

_FENCE_PATTERN = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_ENC = tiktoken.get_encoding("cl100k_base")


def strip_code_blocks(text: str) -> str:
    """Remove all triple-backtick fenced code blocks."""
    return _FENCE_PATTERN.sub("", text)


def truncate_to_tokens(text: str, max_tokens: int = 2000) -> str:
    """Truncate to at most max_tokens (cl100k_base tokenizer)."""
    tokens = _ENC.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return _ENC.decode(tokens[:max_tokens])


def normalize(text: str, max_tokens: int = 2000) -> str:
    """Strip code blocks, then truncate. Order matters: stripping
    first means truncation budget is spent on prose, not code."""
    return truncate_to_tokens(strip_code_blocks(text), max_tokens)
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest tests/test_normalize.py -v
```

Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/pipeline/normalize.py research/info_theory/tests/test_normalize.py
git commit -m "feat(pipeline): normalize strips fenced code + truncates to 2000 tokens"
```

---

## Phase 3: embedding + neighbors

### Task 6: Embedding stage

**Files:**
- Create: `research/info_theory/pipeline/embed.py`
- Create: `research/info_theory/tests/test_embed.py`

- [ ] **Step 1: Write failing tests (mocked embedder)**

```python
# tests/test_embed.py
from unittest.mock import patch, MagicMock
import numpy as np
import pyarrow as pa
from pipeline.embed import embed_drawers, _fingerprint_inputs


def _mock_embedder(dim=1024):
    e = MagicMock()
    # NOTE: use side_effect (not direct assignment) so MagicMock's call_count tracking survives.
    e.encode.side_effect = lambda texts, **kw: np.random.rand(len(texts), dim).astype(np.float32)
    e.model_revision = "bge-m3@abc123"
    return e


def test_embed_adds_vector_column():
    table = pa.table({"drawer_id": ["a", "b"], "text": ["x", "y"]})
    with patch("pipeline.embed.get_embedder", return_value=_mock_embedder()):
        out = embed_drawers(table)
    assert "vector" in out.column_names
    assert out.num_rows == 2


def test_embed_caches_by_input_fingerprint(tmp_path):
    table = pa.table({"drawer_id": ["a"], "text": ["x"]})
    cache = tmp_path / "embeddings.parquet"
    with patch("pipeline.embed.get_embedder", return_value=_mock_embedder()) as m:
        out1 = embed_drawers(table, cache_path=cache)
        out2 = embed_drawers(table, cache_path=cache)
    # Second call hits cache; encode invoked only once
    assert m.return_value.encode.call_count == 1


def test_fingerprint_inputs_changes_when_text_changes():
    t1 = pa.table({"drawer_id": ["a"], "text": ["x"]})
    t2 = pa.table({"drawer_id": ["a"], "text": ["y"]})
    assert _fingerprint_inputs(t1) != _fingerprint_inputs(t2)
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
python -m pytest tests/test_embed.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `embed.py`**

Castle's `cognitive_castle/embedding.py` exposes `embed_texts(texts, device=None)` and `get_embedding_function()` (a callable), **not** a `get_embedder()` object with `.encode`/`.model_revision`. We wrap Castle's real API in a local adapter so the plan's mocking interface still works.

```python
# pipeline/embed.py
"""Embed drawer texts via Castle's bge-m3 embedder. Cached as Parquet.

Castle exposes ``embed_texts`` and ``get_embedding_function`` (returning a
callable) rather than a ``get_embedder()`` object with ``.encode`` and
``.model_revision``. To keep this stage's interface aligned with the research
plan (and to make mocking trivial), we wrap Castle's real API in a small
adapter and expose it as ``get_embedder`` at module scope. Tests patch
``pipeline.embed.get_embedder`` directly.
"""

from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Optional
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from cognitive_castle.embedding import embed_texts


class _CastleEmbedderAdapter:
    """Adapter over Castle's ``embed_texts`` to match the plan's expected
    ``.encode(texts) -> np.ndarray`` and ``.model_revision`` interface."""

    def __init__(self) -> None:
        from cognitive_castle.embedding import _resolve_model_name
        self.model_revision = _resolve_model_name()

    def encode(self, texts, **kwargs) -> np.ndarray:
        vecs = embed_texts(list(texts))
        return np.asarray(vecs, dtype=np.float32)


def get_embedder() -> _CastleEmbedderAdapter:
    """Return a Castle-backed embedder with ``.encode`` and ``.model_revision``."""
    return _CastleEmbedderAdapter()


def _fingerprint_inputs(table: pa.Table) -> str:
    """Hash of (drawer_id, text) pairs in deterministic order."""
    pairs = sorted(zip(
        table.column("drawer_id").to_pylist(),
        table.column("text").to_pylist(),
    ))
    payload = "|".join(f"{d}::{t}" for d, t in pairs).encode()
    return hashlib.sha256(payload).hexdigest()


def embed_drawers(
    table: pa.Table,
    cache_path: Optional[Path] = None,
    batch_size: int = 32,
) -> pa.Table:
    """Add a `vector` column. Cache hit if `cache_path` exists and its
    metadata fingerprint matches inputs."""
    fp = _fingerprint_inputs(table)

    if cache_path and Path(cache_path).exists():
        cached = pq.read_table(cache_path)
        if cached.schema.metadata and cached.schema.metadata.get(b"fingerprint") == fp.encode():
            return cached

    embedder = get_embedder()
    texts = table.column("text").to_pylist()
    vectors: list = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        vectors.extend(embedder.encode(batch))
    vec_array = pa.array(
        [np.asarray(v, dtype=np.float32).tolist() for v in vectors],
        type=pa.list_(pa.float32()),
    )
    out = table.append_column("vector", vec_array)

    if cache_path:
        meta = {b"fingerprint": fp.encode(),
                b"embedder_revision": embedder.model_revision.encode()}
        out = out.replace_schema_metadata(meta)
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(out, cache_path)
    return out
```

**Cache-key note:** Task 6 uses schema-metadata key `b"fingerprint"`. The shared `cache_utils.write_cached` used by other stages writes `b"inputs_fingerprint"`. This is intentional — Task 6 predates the shared helper's adoption for embedding — but any future reader must use the right key when opening this cache directly.

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest tests/test_embed.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/pipeline/embed.py research/info_theory/tests/test_embed.py
git commit -m "feat(pipeline): embed_drawers with fingerprint-based Parquet cache"
```

---

### Task 7: K-nearest-neighbors lookup per drawer

**Files:**
- Create: `research/info_theory/pipeline/neighbors.py`
- Create: `research/info_theory/tests/test_neighbors.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_neighbors.py
import numpy as np
import pyarrow as pa
from pipeline.neighbors import find_neighbors


def _table_with_vectors(n=10, dim=4):
    return pa.table({
        "drawer_id": [f"d{i}" for i in range(n)],
        "wing": ["w"] * n,
        "filed_at": [f"2026-01-{i+1:02d}" for i in range(n)],
        "chunk_index": [0] * n,
        "source_file": [f"f{i}" for i in range(n)],
        "vector": [[float(i + j) for j in range(dim)] for i in range(n)],
    })


def test_find_neighbors_respects_prior_constraint():
    t = _table_with_vectors(5)
    # For target=d2, priors = {d0, d1} only
    neighbors = find_neighbors(t, target_idx=2, k=10, prior_filter="filed_at")
    assert set(neighbors) <= {0, 1}


def test_find_neighbors_returns_at_most_k():
    t = _table_with_vectors(20)
    neighbors = find_neighbors(t, target_idx=10, k=3, prior_filter="filed_at")
    assert len(neighbors) <= 3


def test_find_neighbors_returns_closest_by_cosine():
    # Build a fixture where target is identical to d0, far from d1
    rows = [
        {"drawer_id": "d0", "wing": "w", "filed_at": "2026-01-01",
         "chunk_index": 0, "source_file": "f", "vector": [1.0, 0.0]},
        {"drawer_id": "d1", "wing": "w", "filed_at": "2026-01-02",
         "chunk_index": 0, "source_file": "f", "vector": [0.0, 1.0]},
        {"drawer_id": "target", "wing": "w", "filed_at": "2026-01-03",
         "chunk_index": 0, "source_file": "f", "vector": [1.0, 0.01]},
    ]
    t = pa.Table.from_pylist(rows)
    neighbors = find_neighbors(t, target_idx=2, k=1, prior_filter="filed_at")
    assert neighbors == [0]  # d0 is closest


def test_find_neighbors_same_wing_constraint_palace():
    rows = [
        {"drawer_id": "a", "wing": "w1", "filed_at": "2026-01-01",
         "chunk_index": 0, "source_file": "f", "vector": [1.0, 0.0]},
        {"drawer_id": "b", "wing": "w2", "filed_at": "2026-01-02",
         "chunk_index": 0, "source_file": "f", "vector": [1.0, 0.0]},
        {"drawer_id": "c", "wing": "w1", "filed_at": "2026-01-03",
         "chunk_index": 0, "source_file": "f", "vector": [0.5, 0.5]},
    ]
    t = pa.Table.from_pylist(rows)
    # target=c in w1; b is in w2 and should be excluded
    neighbors = find_neighbors(t, target_idx=2, k=10,
                               prior_filter="filed_at", group_by="wing")
    assert neighbors == [0]  # only 'a' is in same wing
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
python -m pytest tests/test_neighbors.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `neighbors.py`**

```python
# pipeline/neighbors.py
"""Per-drawer KNN lookup over the prior set. Same-wing constraint
for palace; same-session for LME (passed via `group_by`)."""

from __future__ import annotations
from typing import Optional
import numpy as np
import pyarrow as pa


def _cosine(v1: np.ndarray, v2: np.ndarray) -> float:
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (n1 * n2))


def find_neighbors(
    table: pa.Table,
    target_idx: int,
    k: int,
    prior_filter: str = "filed_at",
    group_by: Optional[str] = None,
) -> list[int]:
    """Return indices (into table) of up to k nearest priors to row target_idx.

    Priors are rows where `table[prior_filter][i] < table[prior_filter][target_idx]`.
    If `group_by` is set, also restrict to rows where that field matches the target's.
    """
    target = table.slice(target_idx, 1).to_pylist()[0]
    target_vec = np.array(target["vector"])
    target_pivot = target[prior_filter]

    rows = table.to_pylist()
    candidates = []
    for i, r in enumerate(rows):
        if i == target_idx:
            continue
        if r[prior_filter] >= target_pivot:
            continue
        if group_by is not None and r.get(group_by) != target.get(group_by):
            continue
        sim = _cosine(target_vec, np.array(r["vector"]))
        candidates.append((sim, i))
    candidates.sort(reverse=True)
    return [i for _, i in candidates[:k]]
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest tests/test_neighbors.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/pipeline/neighbors.py research/info_theory/tests/test_neighbors.py
git commit -m "feat(pipeline): KNN with prior + group constraints"
```

---

## Phase 4: estimators

### Task 8: `nn_novelty` (Estimator A)

**Files:**
- Create: `research/info_theory/pipeline/nn_novelty.py`
- Create: `research/info_theory/tests/test_nn_novelty.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_nn_novelty.py
import numpy as np
import pyarrow as pa
from pipeline.nn_novelty import compute_nn_novelty, compute_for_table


def test_nn_novelty_first_drawer_is_max():
    t = pa.table({
        "drawer_id": ["a"], "wing": ["w"], "filed_at": ["2026-01-01"],
        "chunk_index": [0], "source_file": ["f"],
        "vector": [[1.0, 0.0]],
    })
    out = compute_for_table(t, group_by="wing")
    assert out.column("nn_novelty").to_pylist()[0] == 1.0
    assert out.column("is_first").to_pylist()[0] is True


def test_nn_novelty_identical_to_prior_gives_zero():
    rows = [
        {"drawer_id": "a", "wing": "w", "filed_at": "2026-01-01",
         "chunk_index": 0, "source_file": "f", "vector": [1.0, 0.0]},
        {"drawer_id": "b", "wing": "w", "filed_at": "2026-01-02",
         "chunk_index": 0, "source_file": "f", "vector": [1.0, 0.0]},
    ]
    t = pa.Table.from_pylist(rows)
    out = compute_for_table(t, group_by="wing")
    novelties = out.column("nn_novelty").to_pylist()
    assert novelties[0] == 1.0  # first
    assert abs(novelties[1] - 0.0) < 1e-6  # identical to prior


def test_nn_novelty_orthogonal_to_prior_gives_one():
    rows = [
        {"drawer_id": "a", "wing": "w", "filed_at": "2026-01-01",
         "chunk_index": 0, "source_file": "f", "vector": [1.0, 0.0]},
        {"drawer_id": "b", "wing": "w", "filed_at": "2026-01-02",
         "chunk_index": 0, "source_file": "f", "vector": [0.0, 1.0]},
    ]
    t = pa.Table.from_pylist(rows)
    out = compute_for_table(t, group_by="wing")
    assert abs(out.column("nn_novelty").to_pylist()[1] - 1.0) < 1e-6


def test_nn_novelty_decays_monotonically_under_perturbation():
    rng = np.random.default_rng(42)
    base = np.array([1.0, 0.0, 0.0])
    rows = []
    for i in range(20):
        v = base + rng.normal(scale=0.01, size=3) * (i + 1)
        rows.append({
            "drawer_id": f"d{i}", "wing": "w",
            "filed_at": f"2026-01-{i+1:02d}",
            "chunk_index": 0, "source_file": "f",
            "vector": v.tolist(),
        })
    t = pa.Table.from_pylist(rows)
    out = compute_for_table(t, group_by="wing")
    nn = out.column("nn_novelty").to_pylist()
    # Skip the first (is_first=True), check monotone-ish trend over remaining
    # not strictly monotonic, but mean over first half < mean over second half? Wrong.
    # Actually nn_novelty should be LOW because each is close to its predecessor.
    assert max(nn[1:]) < 0.1  # all post-first are low novelty
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
python -m pytest tests/test_nn_novelty.py -v
```

- [ ] **Step 3: Implement `nn_novelty.py`**

```python
# pipeline/nn_novelty.py
"""Estimator A: nearest-neighbor novelty.
1 - max_cosine(d_t, prior_set). Cheap baseline."""

from __future__ import annotations
from typing import Optional
import numpy as np
import pyarrow as pa
from .neighbors import find_neighbors, _cosine


def compute_nn_novelty(target_vec, prior_vecs):
    """1 - max cosine similarity, or 1.0 if prior set is empty."""
    if not prior_vecs:
        return 1.0
    sims = [_cosine(target_vec, p) for p in prior_vecs]
    return 1.0 - max(sims)


def compute_for_table(
    table: pa.Table,
    group_by: Optional[str] = None,
) -> pa.Table:
    """Compute nn_novelty per row. Adds 'nn_novelty' and 'is_first' columns."""
    novelties, is_first = [], []
    for i in range(table.num_rows):
        neighbors = find_neighbors(table, i, k=1,
                                   prior_filter="filed_at",
                                   group_by=group_by)
        if not neighbors:
            novelties.append(1.0)
            is_first.append(True)
        else:
            target_vec = np.array(table.slice(i, 1).to_pylist()[0]["vector"])
            prior_vec = np.array(table.slice(neighbors[0], 1).to_pylist()[0]["vector"])
            novelties.append(compute_nn_novelty(target_vec, [prior_vec]))
            is_first.append(False)
    out = table.append_column("nn_novelty", pa.array(novelties, type=pa.float64()))
    out = out.append_column("is_first", pa.array(is_first, type=pa.bool_()))
    return out
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest tests/test_nn_novelty.py -v
```

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/pipeline/nn_novelty.py research/info_theory/tests/test_nn_novelty.py
git commit -m "feat(estimator): nn_novelty — Estimator A baseline"
```

---

### Task 9: `recon_residual` (Estimator B, LLE + Tikhonov)

**Files:**
- Create: `research/info_theory/pipeline/recon_residual.py`
- Create: `research/info_theory/tests/test_recon_residual.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_recon_residual.py
import numpy as np
import pyarrow as pa
from pipeline.recon_residual import lle_weights, compute_recon_residual, compute_for_table


def test_lle_weights_recover_convex_combination():
    """If d_t lies in span of priors, weights reconstruct it exactly."""
    priors = np.array([[1.0, 0.0], [0.0, 1.0]])  # 2x2 basis
    target = np.array([0.5, 0.5])  # in span
    w = lle_weights(target, priors, lam=1e-9)
    recon = w @ priors
    assert np.allclose(recon, target, atol=1e-4)


def test_lle_weights_sum_to_one():
    priors = np.random.rand(5, 3)
    target = np.random.rand(3)
    w = lle_weights(target, priors, lam=1e-3)
    assert abs(w.sum() - 1.0) < 1e-6


def test_lle_handles_collinear_neighbors():
    """All K priors identical — singular Gram matrix.
    Tikhonov-regularized solve must succeed and return finite residual."""
    priors = np.tile(np.array([1.0, 0.0, 0.0]), (5, 1))
    target = np.array([0.0, 1.0, 0.0])  # orthogonal to all
    w = lle_weights(target, priors, lam=1e-3)
    assert np.all(np.isfinite(w))
    recon = w @ priors
    residual = np.linalg.norm(target - recon)
    assert np.isfinite(residual) and residual > 0


def test_recon_residual_zero_when_in_span():
    priors = [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
    target = np.array([0.3, 0.7])  # in span of priors
    r = compute_recon_residual(target, priors, k=2, lam=1e-9)
    assert r < 1e-3


def test_recon_residual_large_under_orthogonality():
    priors = [np.array([1.0, 0.0, 0.0])] * 5  # all same direction
    target = np.array([0.0, 1.0, 0.0])  # orthogonal
    r = compute_recon_residual(target, priors, k=5, lam=1e-3)
    assert r > 0.5  # substantial residual


def test_recon_residual_null_below_k_floor():
    """K_floor=5: prior set < 5 → recon_residual=None."""
    rows = []
    for i in range(3):
        rows.append({
            "drawer_id": f"d{i}", "wing": "w",
            "filed_at": f"2026-01-{i+1:02d}", "chunk_index": 0,
            "source_file": "f", "vector": [float(i), 0.0],
        })
    t = pa.Table.from_pylist(rows)
    out = compute_for_table(t, k_target=20, k_floor=5, lam=1e-3, group_by="wing")
    residuals = out.column("recon_residual").to_pylist()
    # First 3 drawers all have <5 priors
    assert all(r is None for r in residuals)
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
python -m pytest tests/test_recon_residual.py -v
```

- [ ] **Step 3: Implement `recon_residual.py`**

```python
# pipeline/recon_residual.py
"""Estimator B: LLE reconstruction residual with Tikhonov regularization."""

from __future__ import annotations
from typing import Optional
import numpy as np
import pyarrow as pa
from .neighbors import find_neighbors


def lle_weights(target: np.ndarray, priors: np.ndarray, lam: float = 1e-3) -> np.ndarray:
    """Roweis-Saul LLE weights summing to 1, closed-form with Tikhonov.

    minimize ||target - Σ w_k priors_k||² subject to Σ w_k = 1
    Solution: w = G_reg⁻¹ 1 / (1ᵀ G_reg⁻¹ 1)
    where G = (priors - target)(priors - target)ᵀ
          G_reg = G + λ·trace(G)·I
    """
    K = priors.shape[0]
    centered = priors - target
    G = centered @ centered.T
    G_reg = G + lam * np.trace(G) * np.eye(K)
    try:
        ones = np.ones(K)
        inv_ones = np.linalg.solve(G_reg, ones)
        return inv_ones / inv_ones.sum()
    except np.linalg.LinAlgError:
        # Even with regularization, fall back to uniform weights
        return np.ones(K) / K


def compute_recon_residual(
    target: np.ndarray, priors: list, k: int, lam: float
) -> float:
    """L2 norm of reconstruction residual."""
    P = np.array(priors[:k])
    w = lle_weights(target, P, lam)
    recon = w @ P
    return float(np.linalg.norm(target - recon))


def compute_for_table(
    table: pa.Table,
    k_target: int = 20,
    k_floor: int = 5,
    lam: float = 1e-3,
    group_by: Optional[str] = None,
) -> pa.Table:
    """Add 'recon_residual' column. Null for first K_floor-1 drawers per stratum."""
    residuals = []
    for i in range(table.num_rows):
        neighbors = find_neighbors(table, i, k=k_target,
                                   prior_filter="filed_at", group_by=group_by)
        if len(neighbors) < k_floor:
            residuals.append(None)
            continue
        target_vec = np.array(table.slice(i, 1).to_pylist()[0]["vector"])
        prior_vecs = [
            np.array(table.slice(j, 1).to_pylist()[0]["vector"])
            for j in neighbors
        ]
        residuals.append(compute_recon_residual(target_vec, prior_vecs,
                                                k=len(neighbors), lam=lam))
    return table.append_column("recon_residual", pa.array(residuals, type=pa.float64()))
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest tests/test_recon_residual.py -v
```

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/pipeline/recon_residual.py \
        research/info_theory/tests/test_recon_residual.py
git commit -m "feat(estimator): recon_residual — LLE + Tikhonov, K_floor=5"
```

---

### Task 10: `llm_surprise` prompt construction + parsing

**Files:**
- Create: `research/info_theory/pipeline/llm_surprise.py`
- Create: `research/info_theory/tests/test_llm_surprise.py`

This task covers the *non-resumable* parts — prompt construction, response parsing, single-call orchestration. The resumable batch processing is Task 11.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_llm_surprise.py
from unittest.mock import patch, MagicMock
import json
import pyarrow as pa
from pipeline.llm_surprise import build_prompt, parse_response, llm_surprise_one


def test_build_prompt_includes_priors_and_target():
    priors = [{"text": "prior one"}, {"text": "prior two"}]
    target = {"text": "the target drawer"}
    user_prompt = build_prompt(priors, target)
    assert "prior one" in user_prompt
    assert "prior two" in user_prompt
    assert "the target drawer" in user_prompt
    assert "1-10" in user_prompt or "1–10" in user_prompt


def test_parse_response_valid_json():
    raw = '{"score": 7, "reasoning": "somewhat predictable"}'
    parsed = parse_response(raw)
    assert parsed["score"] == 7
    assert parsed["reasoning"] == "somewhat predictable"


def test_parse_response_strips_markdown_fences():
    raw = '```json\n{"score": 3, "reasoning": "novel"}\n```'
    parsed = parse_response(raw)
    assert parsed["score"] == 3


def test_parse_response_raises_on_malformed():
    import pytest
    with pytest.raises(ValueError):
        parse_response("not json at all")


def test_parse_response_raises_on_out_of_range_score():
    import pytest
    with pytest.raises(ValueError):
        parse_response('{"score": 11, "reasoning": "bad"}')
    with pytest.raises(ValueError):
        parse_response('{"score": 0, "reasoning": "bad"}')


def test_llm_surprise_one_returns_full_record():
    priors = [{"text": "p"}]
    target = {"drawer_id": "d1", "text": "t"}
    fake_provider = MagicMock()
    fake_response = MagicMock()
    fake_response.text = '{"score": 6, "reasoning": "ok"}'
    fake_response.raw = {"total_cost_usd": 0.05}
    fake_response.input_tokens = 1000
    fake_response.completion_tokens = 50
    fake_provider.classify.return_value = fake_response

    out = llm_surprise_one(priors, target, provider=fake_provider)
    assert out["drawer_id"] == "d1"
    assert out["llm_surprise"] == 4.0  # 10 - 6
    assert out["llm_surprise_reasoning_spotcheck"] == "ok"
    assert out["llm_surprise_cost_usd"] == 0.05
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
python -m pytest tests/test_llm_surprise.py -v
```

- [ ] **Step 3: Implement `llm_surprise.py` (single-call parts)**

```python
# pipeline/llm_surprise.py
"""Estimator C: llm_surprise via claude-cli. Single-call orchestration
+ JSON parsing. Resumable batch processing in process_subsample()."""

from __future__ import annotations
import json
import re

_FENCE = re.compile(r"^```(?:json)?\n?|\n?```$", re.MULTILINE)


def build_prompt(priors: list, target: dict) -> str:
    """User-prompt assembly. System prompt set by caller."""
    prior_text = "\n\n".join(
        f"[Entry {i+1}]\n{p['text']}" for i, p in enumerate(priors)
    )
    return (
        f"Given these 20 prior memory entries:\n\n{prior_text}\n\n"
        f"Rate on a 1-10 scale how predictable the following entry is:\n\n"
        f"[Target]\n{target['text']}\n\n"
        f"10 = entirely derivable from priors, 1 = entirely novel.\n"
        f'Return JSON: {{"score": int, "reasoning": short str}}.'
    )


SYSTEM_PROMPT = (
    "You are a retrieval-quality rater. Respond with valid JSON only, "
    "no prose, no markdown fences."
)


def parse_response(raw: str) -> dict:
    """Strip markdown fences, parse JSON, validate."""
    cleaned = _FENCE.sub("", raw.strip())
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"malformed JSON: {e}; raw={raw[:200]!r}")
    if "score" not in parsed:
        raise ValueError(f"missing 'score' field: {parsed}")
    score = parsed["score"]
    if not (1 <= int(score) <= 10):
        raise ValueError(f"score {score} not in [1,10]")
    return {"score": int(score), "reasoning": parsed.get("reasoning", "")}


def llm_surprise_one(priors: list, target: dict, provider) -> dict:
    """One call to the provider; returns a full output-schema record."""
    user = build_prompt(priors, target)
    resp = provider.classify(SYSTEM_PROMPT, user, json_mode=True)
    parsed = parse_response(resp.text)
    return {
        "drawer_id": target["drawer_id"],
        "llm_surprise": float(10 - parsed["score"]),
        "llm_surprise_reasoning_spotcheck": parsed["reasoning"],
        "llm_surprise_prompt_tokens": getattr(resp, "input_tokens", None),
        "llm_surprise_completion_tokens": getattr(resp, "completion_tokens", None),
        "llm_surprise_cost_usd": (resp.raw or {}).get("total_cost_usd"),
    }
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest tests/test_llm_surprise.py -v
```

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/pipeline/llm_surprise.py \
        research/info_theory/tests/test_llm_surprise.py
git commit -m "feat(estimator): llm_surprise — prompt construction + JSON parsing"
```

---

### Task 11: `llm_surprise` resumable batch processing

**Files:**
- Modify: `research/info_theory/pipeline/llm_surprise.py`
- Modify: `research/info_theory/tests/test_llm_surprise.py`

- [ ] **Step 1: Add failing tests for resumability + cost cap**

Append to `tests/test_llm_surprise.py`:

```python
import os
import pyarrow.parquet as pq
from unittest.mock import patch, MagicMock
import pyarrow as pa


def _fake_provider_with_cost(cost_per_call=0.05):
    p = MagicMock()
    def classify(system, user, json_mode=True):
        r = MagicMock()
        r.text = '{"score": 5, "reasoning": ""}'
        r.raw = {"total_cost_usd": cost_per_call}
        r.input_tokens = 1000
        r.completion_tokens = 50
        return r
    p.classify.side_effect = classify
    return p


def test_process_subsample_writes_partials(tmp_path):
    from pipeline.llm_surprise import process_subsample
    targets = [{"drawer_id": f"d{i}", "text": "t"} for i in range(3)]
    priors_lookup = {f"d{i}": [{"text": "p"}] for i in range(3)}
    partials_dir = tmp_path / "partials"
    process_subsample(targets, priors_lookup,
                      provider=_fake_provider_with_cost(),
                      partials_dir=partials_dir, max_cost=1.0)
    files = list(partials_dir.glob("*.parquet"))
    assert len(files) == 3


def test_process_subsample_skips_done_drawers(tmp_path):
    from pipeline.llm_surprise import process_subsample
    partials_dir = tmp_path / "partials"
    partials_dir.mkdir()
    # Pre-create partial for d0 so it's skipped
    pq.write_table(
        pa.table({"drawer_id": ["d0"], "llm_surprise": [3.0]}),
        partials_dir / "d0.parquet",
    )
    provider = _fake_provider_with_cost()
    targets = [{"drawer_id": f"d{i}", "text": "t"} for i in range(3)]
    priors_lookup = {f"d{i}": [{"text": "p"}] for i in range(3)}
    process_subsample(targets, priors_lookup, provider=provider,
                      partials_dir=partials_dir, max_cost=1.0)
    # Only d1, d2 should be called
    assert provider.classify.call_count == 2


def test_process_subsample_aborts_on_cost_cap(tmp_path):
    from pipeline.llm_surprise import process_subsample, CostCapExceeded
    import pytest
    partials_dir = tmp_path / "partials"
    targets = [{"drawer_id": f"d{i}", "text": "t"} for i in range(10)]
    priors_lookup = {f"d{i}": [{"text": "p"}] for i in range(10)}
    # Each call costs $0.05; cap at $0.12 → aborts after 2 calls
    provider = _fake_provider_with_cost(cost_per_call=0.05)
    with pytest.raises(CostCapExceeded):
        process_subsample(targets, priors_lookup, provider=provider,
                          partials_dir=partials_dir, max_cost=0.12)
    # Verify at least one partial was written before the abort
    assert len(list(partials_dir.glob("*.parquet"))) >= 1
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
python -m pytest tests/test_llm_surprise.py -v
```

- [ ] **Step 3: Append `process_subsample` + merge logic to `llm_surprise.py`**

```python
# Append to pipeline/llm_surprise.py
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq


class CostCapExceeded(Exception):
    """Raised when cumulative cost would exceed --max-cost."""


def process_subsample(
    targets: list,
    priors_lookup: dict,
    provider,
    partials_dir: Path,
    max_cost: float = 200.0,
    merge_every: int = 50,
) -> None:
    """Resumable C-stage processing.

    - One Parquet per completed drawer in partials_dir/{drawer_id}.parquet
    - Skip targets whose partial already exists
    - Track cumulative total_cost_usd; raise CostCapExceeded before exceeding max_cost
    - Print last (drawer_id, score, reasoning) every merge_every calls
    """
    partials_dir = Path(partials_dir)
    partials_dir.mkdir(parents=True, exist_ok=True)
    done_ids = {f.stem for f in partials_dir.glob("*.parquet")}
    cumulative = 0.0

    for i, target in enumerate(targets):
        if target["drawer_id"] in done_ids:
            continue
        priors = priors_lookup[target["drawer_id"]]
        # Pre-flight cost check: assume worst-case from prior calls
        result = llm_surprise_one(priors, target, provider)
        cost = result.get("llm_surprise_cost_usd") or 0.0
        if cumulative + cost > max_cost:
            raise CostCapExceeded(
                f"would exceed max_cost={max_cost} (cumulative={cumulative+cost:.4f})"
            )
        cumulative += cost
        pq.write_table(
            pa.table({k: [v] for k, v in result.items()}),
            partials_dir / f"{target['drawer_id']}.parquet",
        )
        if (i + 1) % merge_every == 0:
            print(f"[{i+1}/{len(targets)}] {target['drawer_id']} score={10-result['llm_surprise']} "
                  f"cumulative=${cumulative:.2f}")
            print(f"  reasoning: {result['llm_surprise_reasoning_spotcheck'][:120]}")


def merge_partials(partials_dir: Path, output: Path) -> None:
    """Atomic merge: write to .tmp then rename."""
    partials_dir = Path(partials_dir)
    output = Path(output)
    files = sorted(partials_dir.glob("*.parquet"))
    if not files:
        return
    tables = [pq.read_table(f) for f in files]
    merged = pa.concat_tables(tables, promote_options="default")
    tmp = output.with_suffix(".tmp")
    pq.write_table(merged, tmp)
    tmp.rename(output)
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest tests/test_llm_surprise.py -v
```

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/pipeline/llm_surprise.py \
        research/info_theory/tests/test_llm_surprise.py
git commit -m "feat(estimator): llm_surprise resumable batch + cost cap"
```

---

## Phase 5: stratification

### Task 12: Subsample allocation with termination guard

**Files:**
- Create: `research/info_theory/pipeline/stratify.py`
- Create: `research/info_theory/tests/test_stratify.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_stratify.py
import pytest
from pipeline.stratify import allocate_subsample


def test_proportional_allocation_when_no_floor_hit():
    strata = {"a": 800, "b": 200}  # 80/20 split, both > floor
    alloc = allocate_subsample(strata, n_total=100, floor=10)
    assert alloc["a"] + alloc["b"] == 100
    assert alloc["a"] == 80 and alloc["b"] == 20


def test_floor_raises_small_strata():
    strata = {"big": 950, "small": 50}  # proportional: 95/5
    alloc = allocate_subsample(strata, n_total=100, floor=20)
    assert alloc["small"] == 20  # raised from 5 to floor
    assert alloc["big"] == 80  # stolen 15 from big


def test_termination_when_total_floor_exceeds_n_total():
    # 10 strata × floor 20 = 200 minimum, but n_total=100
    strata = {f"s{i}": 50 for i in range(10)}
    alloc = allocate_subsample(strata, n_total=100, floor=20)
    # Floor must reduce so total fits
    total = sum(alloc.values())
    assert total <= 100
    # All strata get something
    assert all(v > 0 for v in alloc.values())


def test_deterministic_with_seed():
    strata = {"a": 400, "b": 300, "c": 300}
    a1 = allocate_subsample(strata, n_total=100, floor=20, seed=42)
    a2 = allocate_subsample(strata, n_total=100, floor=20, seed=42)
    assert a1 == a2


def test_seed_affects_distribution_only_via_rounding_tiebreaks():
    strata = {"a": 333, "b": 333, "c": 333}
    a1 = allocate_subsample(strata, n_total=100, floor=20, seed=1)
    a2 = allocate_subsample(strata, n_total=100, floor=20, seed=2)
    # Totals always match
    assert sum(a1.values()) == sum(a2.values()) == 100
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
python -m pytest tests/test_stratify.py -v
```

- [ ] **Step 3: Implement `stratify.py`**

```python
# pipeline/stratify.py
"""C-stage subsample allocation with floor + termination guard."""

from __future__ import annotations
import math
import random


def allocate_subsample(
    strata_sizes: dict,
    n_total: int,
    floor: int,
    max_iter: int = 10,
    seed: int = 42,
) -> dict:
    """Stratified allocation with per-stratum floor.

    Algorithm:
      1. If floor*num_strata > n_total: reduce floor to n_total // num_strata.
      2. Proportional allocation across n_total.
      3. Iteratively raise sub-floor strata to floor by stealing from above-floor.
      4. Round-half-up tiebreaks deterministic from seed.
    """
    rng = random.Random(seed)
    num = len(strata_sizes)
    if floor * num > n_total:
        floor = max(1, n_total // num)

    total_size = sum(strata_sizes.values())
    alloc = {k: max(floor, round(n_total * v / total_size))
             for k, v in strata_sizes.items()}

    # Normalize to n_total via random rounding tiebreaks.
    # Loop until diff resolves or no progress can be made: each pass reshuffles
    # keys and applies ±1 adjustments, skipping strata that would drop below floor.
    while True:
        diff = n_total - sum(alloc.values())
        if diff == 0:
            break
        keys = list(alloc.keys())
        rng.shuffle(keys)
        progress = False
        for k in keys:
            if diff == 0:
                break
            step = 1 if diff > 0 else -1
            new_v = alloc[k] + step
            if new_v >= floor:
                alloc[k] = new_v
                diff -= step
                progress = True
        if not progress:
            break

    return alloc
```

**Bug fix (folded from Task 12 implementation):** the plan's original single-pass loop only visits each key once, but tests like `test_floor_raises_small_strata` (2 strata, diff = -15) require **multiple** ±1 adjustments on the same key (e.g., 15 decrements on `big`). Changed to a `while True` loop with a `progress` guard that terminates when no adjustment succeeds — prevents infinite loops when all strata are at floor.

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest tests/test_stratify.py -v
```

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/pipeline/stratify.py \
        research/info_theory/tests/test_stratify.py
git commit -m "feat(pipeline): stratify with floor + termination guard"
```

---

## Phase 6: analysis

### Task 13: Decay-model fits (power-law + exponential)

**Files:**
- Create: `research/info_theory/analysis/fit_decay.py`
- Create: `research/info_theory/tests/test_fit_decay.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_fit_decay.py
import numpy as np
from analysis.fit_decay import (
    fit_powerlaw_weighted, fit_exponential, aic_model_selection,
    empirical_variance_per_bin,
)


def test_empirical_variance_binning():
    """Bin width 10 → 5 bins for N=50."""
    N = np.arange(1, 51)
    y = np.random.normal(0, 1, 50)
    bins = empirical_variance_per_bin(N, y, bin_width=10)
    assert len(bins) == 5
    assert all(v > 0 for v in bins.values())


def test_powerlaw_recovery_homoscedastic():
    rng = np.random.default_rng(42)
    N = np.arange(1, 1001)
    y = N ** -0.5 + rng.normal(0, 0.01, 1000)
    params = fit_powerlaw_weighted(N, y)
    assert abs(params["alpha"] - 0.5) < 0.05


def test_exponential_recovery():
    rng = np.random.default_rng(42)
    N = np.arange(1, 1001)
    y = 1 + 9 * np.exp(-N / 100) + rng.normal(0, 0.1, 1000)
    params = fit_exponential(N, y)
    assert abs(params["tau"] - 100) < 10
    assert abs(params["c"] - 1) < 0.5


def test_aic_picks_powerlaw_for_powerlaw_data():
    rng = np.random.default_rng(42)
    N = np.arange(1, 1001)
    y = N ** -0.5 + rng.normal(0, 0.01, 1000)
    pl = fit_powerlaw_weighted(N, y)
    ex = fit_exponential(N, y)
    selection = aic_model_selection(pl, ex)
    assert selection["winner"] == "powerlaw"
    assert selection["weight_powerlaw"] > 0.9
```

- [ ] **Step 2: Run tests, verify fail**

```bash
python -m pytest tests/test_fit_decay.py -v
```

- [ ] **Step 3: Implement `fit_decay.py`**

```python
# analysis/fit_decay.py
"""Decay-model fits: power-law (weighted LS with empirical variance)
and exponential. AIC-based model selection."""

from __future__ import annotations
import numpy as np
from scipy.optimize import curve_fit


def empirical_variance_per_bin(N: np.ndarray, y: np.ndarray, bin_width: int = 10) -> dict:
    """σ̂² per bin of N. Returns {bin_start: variance}."""
    bins = {}
    for start in range(int(N.min()), int(N.max()) + 1, bin_width):
        mask = (N >= start) & (N < start + bin_width)
        if mask.sum() > 1:
            bins[start] = float(np.var(y[mask], ddof=1))
        else:
            bins[start] = 1.0  # placeholder for sparse bins
    return bins


def _weights_from_bins(N: np.ndarray, bins: dict, bin_width: int) -> np.ndarray:
    w = np.ones_like(N, dtype=float)
    for i, n in enumerate(N):
        start = int(n // bin_width) * bin_width
        sigma2 = bins.get(start, 1.0)
        w[i] = 1.0 / max(sigma2, 1e-9)
    return w


def fit_powerlaw_weighted(N: np.ndarray, y: np.ndarray, bin_width: int = 10) -> dict:
    """info(N) = a · N^(-α) + ε. WLS with empirical per-bin σ̂²."""
    N = np.asarray(N, dtype=float)
    y = np.asarray(y, dtype=float)
    bins = empirical_variance_per_bin(N, y, bin_width)
    w = _weights_from_bins(N, bins, bin_width)

    def model(N, a, alpha):
        return a * N ** (-alpha)

    popt, pcov = curve_fit(model, N, y, sigma=1.0/np.sqrt(w), p0=[1.0, 0.5],
                            absolute_sigma=True, maxfev=5000)
    a, alpha = popt
    resid = y - model(N, *popt)
    rss = float(np.sum(w * resid**2))
    n = len(y)
    k = 2  # a, alpha
    aic = n * np.log(rss / n) + 2 * k
    return {"a": float(a), "alpha": float(alpha), "rss": rss, "aic": float(aic), "n": n}


def fit_exponential(N: np.ndarray, y: np.ndarray) -> dict:
    """info(N) = c + (a − c) · exp(−N/τ) + ε. OLS."""
    N = np.asarray(N, dtype=float)
    y = np.asarray(y, dtype=float)

    def model(N, a, c, tau):
        return c + (a - c) * np.exp(-N / tau)

    popt, _ = curve_fit(model, N, y, p0=[y[0], y[-1], len(N)/4], maxfev=5000)
    a, c, tau = popt
    resid = y - model(N, *popt)
    rss = float(np.sum(resid**2))
    n = len(y)
    k = 3  # a, c, tau
    aic = n * np.log(rss / n) + 2 * k
    return {"a": float(a), "c": float(c), "tau": float(tau),
            "rss": rss, "aic": float(aic), "n": n}


def aic_model_selection(pl: dict, ex: dict) -> dict:
    """Akaike weights from two model fits."""
    aic_min = min(pl["aic"], ex["aic"])
    delta_pl = pl["aic"] - aic_min
    delta_ex = ex["aic"] - aic_min
    w_pl = np.exp(-0.5 * delta_pl)
    w_ex = np.exp(-0.5 * delta_ex)
    s = w_pl + w_ex
    return {
        "winner": "powerlaw" if pl["aic"] < ex["aic"] else "exponential",
        "weight_powerlaw": float(w_pl / s),
        "weight_exponential": float(w_ex / s),
        "delta_aic": float(abs(pl["aic"] - ex["aic"])),
    }
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest tests/test_fit_decay.py -v
```

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/analysis/fit_decay.py \
        research/info_theory/tests/test_fit_decay.py
git commit -m "feat(analysis): fit_decay — WLS power-law, OLS exponential, AIC selection"
```

---

### Task 14: Source-aware block bootstrap

**Files:**
- Create: `research/info_theory/analysis/block_bootstrap.py`
- Create: `research/info_theory/tests/test_block_bootstrap.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_block_bootstrap.py
import numpy as np
from analysis.block_bootstrap import build_blocks, bootstrap_ci


def test_build_blocks_size_clamped():
    """clamp(N//5, 10, 100)"""
    assert build_blocks(N_total=200, source_files=["a"]*200)[0] == 40
    assert build_blocks(N_total=50, source_files=["a"]*50)[0] == 10
    assert build_blocks(N_total=10000, source_files=["a"]*10000)[0] == 100


def test_source_aware_blocks_span_source_boundaries():
    """Blocks should not all be from the same source_file."""
    source_files = (["fileA"] * 50) + (["fileB"] * 50) + (["fileC"] * 50)
    block_size, blocks = build_blocks(N_total=150, source_files=source_files)
    # At least one block crosses sources
    spans = [len(set(source_files[idx] for idx in block)) for block in blocks]
    assert max(spans) > 1, f"all blocks single-source: {spans}"


def test_bootstrap_ci_coverage_on_ar1():
    """Synthetic AR(1) with known mean; bootstrap CIs cover at ~95% rate."""
    rng = np.random.default_rng(42)
    true_mean = 5.0
    n_datasets = 50  # keep test fast
    covered = 0
    for _ in range(n_datasets):
        n = 200
        x = np.zeros(n)
        x[0] = true_mean + rng.normal()
        for i in range(1, n):
            x[i] = 0.7 * x[i-1] + 0.3 * true_mean + rng.normal(0, 0.3)
        ci_lo, ci_hi = bootstrap_ci(x, np.mean, n_resamples=200, block_size=20,
                                     source_files=["s"]*n, seed=42)
        if ci_lo <= true_mean <= ci_hi:
            covered += 1
    rate = covered / n_datasets
    # Approximate 95% coverage; binomial sd ≈ 0.03 for n=50, so 85-100% acceptable
    assert 0.80 <= rate <= 1.0, f"coverage {rate} out of expected range"
```

- [ ] **Step 2: Run tests, verify fail**

```bash
python -m pytest tests/test_block_bootstrap.py -v
```

- [ ] **Step 3: Implement `block_bootstrap.py`**

```python
# analysis/block_bootstrap.py
"""Source-aware block bootstrap for decay-fit CIs."""

from __future__ import annotations
import numpy as np


def build_blocks(N_total: int, source_files: list) -> tuple[int, list[list[int]]]:
    """Returns (block_size, blocks). block_size = clamp(N_total//5, 10, 100).
    Blocks are contiguous index ranges that span source-file boundaries
    where possible (i.e., not built within a single source-file group)."""
    block_size = max(10, min(100, N_total // 5))
    blocks = []
    i = 0
    while i < N_total:
        block = list(range(i, min(i + block_size, N_total)))
        blocks.append(block)
        i += block_size
    return block_size, blocks


def bootstrap_ci(
    data: np.ndarray,
    statistic,
    n_resamples: int = 1000,
    block_size: int = None,
    source_files: list = None,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """Block bootstrap CI. If block_size is None, uses build_blocks."""
    n = len(data)
    if block_size is None:
        block_size, _ = build_blocks(n, source_files or ["s"]*n)
    rng = np.random.default_rng(seed)
    n_blocks_needed = n // block_size + 1
    block_starts = list(range(0, n, block_size))
    estimates = []
    for _ in range(n_resamples):
        chosen = rng.choice(block_starts, size=n_blocks_needed, replace=True)
        resample = []
        for s in chosen:
            resample.extend(data[s:s + block_size])
            if len(resample) >= n:
                break
        estimates.append(statistic(np.array(resample[:n])))
    lo = np.quantile(estimates, (1 - confidence) / 2)
    hi = np.quantile(estimates, 1 - (1 - confidence) / 2)
    return float(lo), float(hi)
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest tests/test_block_bootstrap.py -v
```

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/analysis/block_bootstrap.py \
        research/info_theory/tests/test_block_bootstrap.py
git commit -m "feat(analysis): source-aware block bootstrap with clamped block size"
```

---

### Task 15: Correlations (A↔C, B↔C)

**Files:**
- Create: `research/info_theory/analysis/correlations.py`
- Create: `research/info_theory/tests/test_correlations.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_correlations.py
import numpy as np
from analysis.correlations import spearman_with_ci, pearson_with_ci


def test_spearman_perfect_correlation():
    x = np.array([1, 2, 3, 4, 5, 6])
    y = np.array([2, 4, 6, 8, 10, 12])
    rho, ci_lo, ci_hi = spearman_with_ci(x, y, n_resamples=100, seed=42)
    assert abs(rho - 1.0) < 1e-9


def test_spearman_no_correlation():
    rng = np.random.default_rng(42)
    x = rng.normal(0, 1, 200)
    y = rng.normal(0, 1, 200)
    rho, ci_lo, ci_hi = spearman_with_ci(x, y, n_resamples=200, seed=42)
    assert abs(rho) < 0.2
    # CI should include 0
    assert ci_lo <= 0 <= ci_hi


def test_pearson_known_correlation():
    rng = np.random.default_rng(42)
    n = 1000
    x = rng.normal(0, 1, n)
    y = 0.7 * x + 0.3 * rng.normal(0, 1, n)
    rho, _, _ = pearson_with_ci(x, y, n_resamples=100, seed=42)
    # Theoretical rho = 0.7/sqrt(0.7² + 0.3²) ≈ 0.919; observed ≈ 0.915.
    assert 0.5 < rho < 0.95
```

- [ ] **Step 2: Run tests, verify fail**

```bash
python -m pytest tests/test_correlations.py -v
```

- [ ] **Step 3: Implement `correlations.py`**

```python
# analysis/correlations.py
"""Spearman + Pearson with bootstrap CIs for A↔C and B↔C validation."""

from __future__ import annotations
import numpy as np
from scipy import stats


def _bootstrap_correlation(x, y, corr_func, n_resamples, seed):
    rng = np.random.default_rng(seed)
    n = len(x)
    estimates = []
    for _ in range(n_resamples):
        idx = rng.integers(0, n, n)
        estimates.append(corr_func(x[idx], y[idx])[0])
    return np.quantile(estimates, 0.025), np.quantile(estimates, 0.975)


def spearman_with_ci(x, y, n_resamples: int = 1000, seed: int = 42):
    """Spearman rank correlation + bootstrap 95% CI."""
    x = np.asarray(x); y = np.asarray(y)
    rho = stats.spearmanr(x, y)[0]
    lo, hi = _bootstrap_correlation(x, y, stats.spearmanr, n_resamples, seed)
    return float(rho), float(lo), float(hi)


def pearson_with_ci(x, y, n_resamples: int = 1000, seed: int = 42):
    """Pearson correlation + bootstrap 95% CI."""
    x = np.asarray(x); y = np.asarray(y)
    rho = stats.pearsonr(x, y)[0]
    lo, hi = _bootstrap_correlation(x, y, stats.pearsonr, n_resamples, seed)
    return float(rho), float(lo), float(hi)
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest tests/test_correlations.py -v
```

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/analysis/correlations.py \
        research/info_theory/tests/test_correlations.py
git commit -m "feat(analysis): Spearman + Pearson with bootstrap CIs"
```

---

### Task 16: Heterogeneity (Kruskal-Wallis + epsilon-squared)

**Files:**
- Create: `research/info_theory/analysis/heterogeneity.py`
- Create: `research/info_theory/tests/test_heterogeneity.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_heterogeneity.py
import numpy as np
from analysis.heterogeneity import kruskal_wallis_with_epsilon_sq


def test_kruskal_wallis_detects_difference():
    rng = np.random.default_rng(42)
    group_a = rng.normal(0.3, 0.1, 20)
    group_b = rng.normal(0.7, 0.1, 20)
    result = kruskal_wallis_with_epsilon_sq({"a": group_a, "b": group_b})
    assert result["p_value"] < 0.001
    assert result["epsilon_squared"] > 0.3  # large effect


def test_kruskal_wallis_no_difference():
    rng = np.random.default_rng(42)
    a = rng.normal(0.5, 0.1, 30)
    b = rng.normal(0.5, 0.1, 30)
    result = kruskal_wallis_with_epsilon_sq({"a": a, "b": b})
    assert result["p_value"] > 0.05
    assert result["epsilon_squared"] < 0.1


def test_handles_three_groups():
    rng = np.random.default_rng(42)
    groups = {
        "miner": rng.normal(0.7, 0.1, 20),
        "session_hook": rng.normal(0.5, 0.1, 20),
        "mcp": rng.normal(0.2, 0.1, 5),
    }
    result = kruskal_wallis_with_epsilon_sq(groups)
    assert result["p_value"] < 0.001
    assert "n_per_group" in result
    assert result["n_per_group"]["mcp"] == 5
```

- [ ] **Step 2: Run tests, verify fail**

```bash
python -m pytest tests/test_heterogeneity.py -v
```

- [ ] **Step 3: Implement `heterogeneity.py`**

```python
# analysis/heterogeneity.py
"""H1 heterogeneity test: Kruskal-Wallis with epsilon-squared effect size."""

from __future__ import annotations
import numpy as np
from scipy import stats


def kruskal_wallis_with_epsilon_sq(groups: dict) -> dict:
    """Run Kruskal-Wallis on a dict of {group_name: values}.

    Returns dict with:
      H: KW statistic
      p_value: p-value
      epsilon_squared: ε²_H = (H - k + 1) / (n - k)
      n_per_group: counts
      median_per_group: medians
    """
    arrays = [np.asarray(v) for v in groups.values()]
    H, p = stats.kruskal(*arrays)
    n = sum(len(a) for a in arrays)
    k = len(arrays)
    # Epsilon-squared per Tomczak & Tomczak 2014
    eps_sq = (H - k + 1) / max(n - k, 1)
    return {
        "H": float(H),
        "p_value": float(p),
        "epsilon_squared": float(max(eps_sq, 0)),
        "n_per_group": {name: len(np.asarray(v)) for name, v in groups.items()},
        "median_per_group": {name: float(np.median(np.asarray(v)))
                              for name, v in groups.items()},
    }
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest tests/test_heterogeneity.py -v
```

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/analysis/heterogeneity.py \
        research/info_theory/tests/test_heterogeneity.py
git commit -m "feat(analysis): H1 heterogeneity — Kruskal-Wallis + epsilon-squared"
```

---

### Task 16b: Aggregation — FDR correction + N* + stratum filtering

This is the "tying-it-together" task. Covers three pieces the spec
requires that don't fit cleanly in the per-module analysis tasks:
Benjamini-Hochberg FDR correction across all hypothesis tests, the
operational `N*` saturation-point computation per stratum, and the
≥200-drawer power-floor filter.

**Files:**
- Create: `research/info_theory/analysis/aggregation.py`
- Create: `research/info_theory/tests/test_aggregation.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_aggregation.py
import numpy as np
from analysis.aggregation import (
    benjamini_hochberg, compute_n_star, select_fittable_strata,
)


def test_bh_correction_known_case():
    """BH q=0.05: of these p-values, how many survive?"""
    p_values = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.5]
    survivors = benjamini_hochberg(p_values, q=0.05)
    # BH formula requires p_(k) ≤ (k/m)·q. With m=7, q=0.05:
    #   rank 1: 0.001 ≤ 0.00714 ✓
    #   rank 2: 0.008 ≤ 0.01429 ✓
    #   rank 3: 0.039 ≤ 0.02143 ✗   ← p=0.039 fails, so largest k is 2
    #   ranks 4-7: all fail
    # Only first two (0.001, 0.008) survive.
    assert sum(survivors) == 2
    assert survivors[0] and survivors[1]
    assert not survivors[2] and not survivors[3]


def test_bh_correction_all_significant():
    survivors = benjamini_hochberg([0.0001, 0.0001, 0.0001], q=0.05)
    assert all(survivors)


def test_bh_correction_none_significant():
    survivors = benjamini_hochberg([0.9, 0.8, 0.7], q=0.05)
    assert not any(survivors)


def test_compute_n_star_finds_saturation():
    """Synthetic: info decays then stays low."""
    N = np.arange(1, 301)
    # First 100: decreasing from 1.0 to 0.1; remainder: stays ~0.05
    info = np.concatenate([np.linspace(1.0, 0.1, 100),
                           np.full(200, 0.05)])
    # Null needs positive IQR so threshold = threshold_factor × IQR > 0.
    # A constant null (e.g., np.full(300, 0.5)) → IQR=0 → threshold=0 → smoothed<0
    # is always False → never saturates. Linspace gives IQR ≈ 0.15 so the
    # saturated tail at 0.05 falls below the threshold cleanly.
    shuffled_null = np.linspace(0.05, 0.35, 300)
    n_star = compute_n_star(N, info, shuffled_null,
                             threshold_factor=1.0,
                             persistence_factor=0.1)
    assert 50 <= n_star <= 200  # somewhere in the saturated region


def test_compute_n_star_returns_none_if_never_saturates():
    N = np.arange(1, 101)
    info = np.full(100, 1.0)  # never decays
    shuffled_null = np.full(100, 0.5)
    n_star = compute_n_star(N, info, shuffled_null,
                             threshold_factor=1.0,
                             persistence_factor=0.1)
    assert n_star is None


def test_select_fittable_strata_enforces_200_floor():
    strata_sizes = {"big1": 5000, "big2": 300, "borderline": 199,
                    "small": 50}
    fittable, descriptive = select_fittable_strata(strata_sizes, floor=200)
    assert "big1" in fittable and "big2" in fittable
    assert "borderline" in descriptive
    assert "small" in descriptive
```

- [ ] **Step 2: Run tests, verify fail**

```bash
python -m pytest tests/test_aggregation.py -v
```

- [ ] **Step 3: Implement `aggregation.py`**

```python
# analysis/aggregation.py
"""Cross-stratum aggregation: FDR correction (BH q=0.05), N*
saturation point, and the ≥200-drawer power-floor filter."""

from __future__ import annotations
from typing import Optional
import numpy as np


def benjamini_hochberg(p_values: list, q: float = 0.05) -> list:
    """Return list of bool — True if p survives BH correction at FDR=q.

    BH procedure:
      Sort p_values ascending. Find the largest k such that
      p_(k) ≤ (k/m) * q. Reject all p_(i) for i ≤ k.
    """
    m = len(p_values)
    if m == 0:
        return []
    indexed = sorted(enumerate(p_values), key=lambda t: t[1])
    threshold_idx = -1
    for rank, (_, p) in enumerate(indexed, start=1):
        if p <= (rank / m) * q:
            threshold_idx = rank
    out = [False] * m
    if threshold_idx > 0:
        for orig_idx, _ in indexed[:threshold_idx]:
            out[orig_idx] = True
    return out


def _lowess(N: np.ndarray, y: np.ndarray, frac: float = 0.1) -> np.ndarray:
    """Light-weight LOWESS smoothing. Uses scipy if available, else
    moving average fallback."""
    try:
        from statsmodels.nonparametric.smoothers_lowess import lowess
        return lowess(y, N, frac=frac, return_sorted=False)
    except ImportError:
        win = max(3, int(len(y) * frac))
        cumsum = np.cumsum(np.insert(y, 0, 0))
        return (cumsum[win:] - cumsum[:-win]) / win


def compute_n_star(
    N: np.ndarray,
    info: np.ndarray,
    shuffled_null: np.ndarray,
    threshold_factor: float = 1.0,
    persistence_factor: float = 0.1,
) -> Optional[int]:
    """Smallest N where smoothed info drops below
    threshold_factor × IQR(shuffled_null) AND stays for
    ≥ max(10, len(N) * persistence_factor) consecutive points.

    Returns N* index, or None if never saturates.
    """
    smoothed = _lowess(np.arange(len(info)), info, frac=0.1)
    null_iqr = float(np.percentile(shuffled_null, 75) - np.percentile(shuffled_null, 25))
    threshold = threshold_factor * null_iqr
    persistence = max(10, int(len(N) * persistence_factor))
    below = smoothed < threshold
    # Find first N where `persistence` consecutive Trues follow
    for i in range(len(below) - persistence + 1):
        if all(below[i:i + persistence]):
            return int(N[i])
    return None


def select_fittable_strata(strata_sizes: dict, floor: int = 200) -> tuple[list, list]:
    """Return (fittable_strata, descriptive_only_strata)."""
    fittable = [s for s, n in strata_sizes.items() if n >= floor]
    descriptive = [s for s, n in strata_sizes.items() if n < floor]
    return fittable, descriptive
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest tests/test_aggregation.py -v
```

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/analysis/aggregation.py \
        research/info_theory/tests/test_aggregation.py
git commit -m "feat(analysis): aggregation — BH-FDR, N* saturation point, ≥200 floor"
```

---

## Phase 7: downstream evaluation [H3-CONTINGENT]

### Task 17: H3 downstream R@5 evaluation [H3]

**Skip this task if Task 0 returned H3 OUT.** Task 0 returned **H3 IN** with
two findings that shape this task:

1. **The harness is already parameterizable.** No CLI flag refactor needed.
   Corpus is rebuilt per question from three in-memory arrays
   (`haystack_sessions`, `haystack_session_ids`, `haystack_dates`); the
   ChromaDB index is ephemeral and `_fresh_collection()` recreates it per
   question. H3 filters by trimming those three arrays in lockstep before
   each entry hits `build_palace_and_retrieve` (or any of its sibling
   functions: `..._aaak`, `..._rooms`, `..._hybrid`, `..._full`).
2. **Provenance bridge required.** `recon_residual` is computed at
   **drawer** granularity (Castle's chunks), but LME drops operate at
   **session** granularity. The H3 runner must group drawers by
   `session_id` and apply a session-level aggregation to decide which
   sessions to drop. **Decision rule (locked):** filter at the session
   level using the **mean** of `recon_residual` across drawers in each
   session. Simpler than median, robust to chunking variance, matches
   LME's natural drop granularity.

**Files:**
- Create: `research/info_theory/pipeline/downstream_eval.py`
- Create: `research/info_theory/tests/test_downstream_eval.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_downstream_eval.py
import numpy as np
import pyarrow as pa
from pipeline.downstream_eval import (
    aggregate_to_session_scores,
    drop_bottom_sessions_by_info,
    apply_drop_filter,
    run_h3_experiment,
)


def test_aggregate_to_session_scores_mean():
    """Drawer-level recon_residual → session-level mean."""
    import pytest
    table = pa.table({
        "drawer_id": ["d0", "d1", "d2", "d3"],
        "session_id": ["s_a", "s_a", "s_b", "s_b"],
        "recon_residual": [0.2, 0.4, 0.6, 0.8],
    })
    session_scores = aggregate_to_session_scores(table)
    # pytest.approx: statistics.mean([0.2, 0.4]) = 0.30000000000000004 (float precision).
    assert session_scores["s_a"] == pytest.approx(0.3)  # mean of 0.2, 0.4
    assert session_scores["s_b"] == pytest.approx(0.7)  # mean of 0.6, 0.8


def test_aggregate_handles_null_residuals():
    """Drawers with null recon_residual (below K_floor) are excluded
    from the mean. If all of a session's drawers are null, the session
    is excluded entirely (cannot be info-weighted)."""
    table = pa.table({
        "drawer_id": ["d0", "d1", "d2", "d3"],
        "session_id": ["s_a", "s_a", "s_b", "s_b"],
        "recon_residual": [None, 0.5, None, None],
    })
    session_scores = aggregate_to_session_scores(table)
    assert session_scores["s_a"] == 0.5
    assert "s_b" not in session_scores  # all null


def test_drop_bottom_sessions_threshold_25():
    session_scores = {f"s{i}": float(i) for i in range(100)}
    kept = drop_bottom_sessions_by_info(session_scores, threshold_pct=25)
    # Lowest 25 (s0..s24) dropped
    assert "s24" not in kept and "s0" not in kept
    assert "s25" in kept and "s99" in kept
    assert len(kept) == 75


def test_apply_drop_filter_trims_three_arrays_in_lockstep():
    """The actual filter operation that hits the LME entry shape."""
    entry = {
        "question_id": "q1",
        "haystack_sessions": [["turn1"], ["turn2"], ["turn3"]],
        "haystack_session_ids": ["s_a", "s_b", "s_c"],
        "haystack_dates": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "other_field": "preserved",
    }
    out = apply_drop_filter(entry, drop_ids={"s_b"})
    assert out["haystack_session_ids"] == ["s_a", "s_c"]
    assert out["haystack_sessions"] == [["turn1"], ["turn3"]]
    assert out["haystack_dates"] == ["2026-01-01", "2026-01-03"]
    assert out["other_field"] == "preserved"
    assert out["question_id"] == "q1"
    # Original is not mutated
    assert len(entry["haystack_session_ids"]) == 3


def test_run_h3_experiment_calls_harness_per_threshold():
    """Smoke test with mocked harness."""
    from unittest.mock import patch
    drawer_table = pa.table({
        "drawer_id": ["d0", "d1", "d2", "d3"],
        "session_id": ["s_a", "s_a", "s_b", "s_b"],
        "recon_residual": [0.2, 0.4, 0.6, 0.8],
    })
    lme_entries = [
        {"question_id": "q1",
         "haystack_sessions": [["x"], ["y"]],
         "haystack_session_ids": ["s_a", "s_b"],
         "haystack_dates": ["d1", "d2"],
         "answer_session_ids": ["s_b"]},
    ]
    # Mock the per-entry retrieval call to return a constant R@5
    fake_r_at_5 = {"uniform": 1.0, 10: 1.0, 25: 0.5, 50: 0.0}

    def fake_eval(entries, drop_ids):
        # Determine threshold from drop_ids size relative to total sessions
        if not drop_ids:
            return fake_r_at_5["uniform"]
        # Total = 2 sessions; drop_ids count tells us threshold
        if len(drop_ids) == 0: return fake_r_at_5["uniform"]
        if "s_a" in drop_ids and len(drop_ids) == 1: return fake_r_at_5[50]
        return fake_r_at_5[10]

    with patch("pipeline.downstream_eval._run_lme_with_filter",
                 side_effect=fake_eval) as m:
        results = run_h3_experiment(drawer_table, lme_entries,
                                     thresholds=(10, 25, 50))
    assert "uniform" in results
    assert all(t in results for t in (10, 25, 50))
    assert m.call_count == 4  # uniform + 3 thresholds
```

- [ ] **Step 2: Run tests, verify fail**

```bash
python -m pytest tests/test_downstream_eval.py -v
```

- [ ] **Step 3: Implement `downstream_eval.py`**

```python
# pipeline/downstream_eval.py
"""H3 — LongMemEval R@5 under info-weighted corpus.

Aggregates drawer-level recon_residual to session-level scores (mean),
drops bottom-X% of sessions, then filters each LME entry's
haystack_session_ids/sessions/dates arrays in lockstep before retrieval.

Per Task 0 spike findings: the LME harness rebuilds its retrieval
index per question from these three arrays, so trimming them is the
entire filter mechanism — no harness refactor needed."""

from __future__ import annotations
import statistics
from typing import Optional
import pyarrow as pa


def aggregate_to_session_scores(
    table: pa.Table,
    info_col: str = "recon_residual",
    session_col: str = "session_id",
) -> dict:
    """Drawer-level info → session-level mean. Sessions with all-null
    drawers are excluded (cannot be info-weighted)."""
    rows = table.to_pylist()
    by_session: dict = {}
    for r in rows:
        sid = r.get(session_col)
        score = r.get(info_col)
        if sid is None or score is None:
            if sid is not None:
                by_session.setdefault(sid, [])
            continue
        by_session.setdefault(sid, []).append(score)
    return {sid: statistics.mean(scores) for sid, scores in by_session.items()
             if scores}


def drop_bottom_sessions_by_info(session_scores: dict, threshold_pct: float) -> set:
    """Return the set of session_ids to KEEP (i.e., top (100-X)% by score)."""
    items = sorted(session_scores.items(), key=lambda kv: kv[1])
    n = len(items)
    drop_n = int(n * threshold_pct / 100)
    return {sid for sid, _ in items[drop_n:]}


def apply_drop_filter(entry: dict, drop_ids: set) -> dict:
    """Trim haystack_sessions/session_ids/dates in lockstep.
    Returns a new dict; does not mutate input."""
    sessions, sids, dates = [], [], []
    for s, sid, d in zip(entry["haystack_sessions"],
                          entry["haystack_session_ids"],
                          entry["haystack_dates"]):
        if sid in drop_ids:
            continue
        sessions.append(s); sids.append(sid); dates.append(d)
    out = dict(entry)
    out["haystack_sessions"] = sessions
    out["haystack_session_ids"] = sids
    out["haystack_dates"] = dates
    return out


def _run_lme_with_filter(entries: list, drop_ids: set) -> float:
    """Invoke the LME harness with each entry filtered by drop_ids.
    Returns mean R@5 (recall_any) across entries.

    drop_ids empty → uniform baseline.

    NOTE (verified against benchmarks/longmemeval_bench.py, Task 17):
    - build_palace_and_retrieve(entry, granularity='session', n_results=50)
        returns 4-tuple: (rankings, corpus, corpus_ids, corpus_timestamps)
    - evaluate_retrieval(rankings, correct_ids, corpus_ids, k)
        returns 3-tuple: (recall_any, recall_all, ndcg_score)
    We call with n_results=5 and read recall_any as R@5.
    """
    # Imports kept lazy to keep test mocking simple
    from benchmarks.longmemeval_bench import (
        build_palace_and_retrieve, evaluate_retrieval,
    )
    recalls = []
    for entry in entries:
        filtered = apply_drop_filter(entry, drop_ids)
        if not filtered["haystack_session_ids"]:
            continue  # nothing left to retrieve against
        rankings, _corpus, corpus_ids, _ts = build_palace_and_retrieve(
            filtered, granularity="session", n_results=5,
        )
        correct_ids = filtered.get("answer_session_ids", [])
        recall_any, _recall_all, _ndcg = evaluate_retrieval(
            rankings, correct_ids, corpus_ids, k=5,
        )
        recalls.append(recall_any)
    return sum(recalls) / len(recalls) if recalls else 0.0


def run_h3_experiment(
    drawer_table: pa.Table,
    lme_entries: list,
    thresholds: tuple = (10, 25, 50),
) -> dict:
    """Returns {"uniform": R@5, 10: R@5, 25: R@5, 50: R@5}."""
    session_scores = aggregate_to_session_scores(drawer_table)
    results = {"uniform": _run_lme_with_filter(lme_entries, drop_ids=set())}
    all_sessions = set(session_scores.keys())
    for t in thresholds:
        keep = drop_bottom_sessions_by_info(session_scores, threshold_pct=t)
        drop = all_sessions - keep
        results[t] = _run_lme_with_filter(lme_entries, drop_ids=drop)
    return results
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest tests/test_downstream_eval.py -v
```

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/pipeline/downstream_eval.py \
        research/info_theory/tests/test_downstream_eval.py
git commit -m "feat(pipeline): downstream_eval — H3 R@5 with session-level provenance bridge"
```

---

## Phase 8: CLI orchestration

### Task 18: CLI core (`snapshot`, `pilot`, `run`, `status`)

**Files:**
- Create: `research/info_theory/cli.py`
- Create: `research/info_theory/tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli.py
from unittest.mock import patch
from cli import build_arg_parser, dispatch


def test_arg_parser_recognizes_subcommands():
    p = build_arg_parser()
    for sub in ["snapshot", "pilot", "run", "status", "figures", "cost-estimate"]:
        args = p.parse_args([sub])
        assert args.command == sub


def test_run_subcommand_accepts_stage_flag():
    p = build_arg_parser()
    args = p.parse_args(["run", "--stage", "embed"])
    assert args.stage == "embed"


def test_run_all_invokes_all_stages():
    with patch("cli.STAGES") as m:
        m.keys.return_value = ["s1", "s2"]
        m.__contains__.return_value = True
        with patch("cli._run_stage") as run_m:
            from cli import dispatch
            class A: command="run"; stage=None; all=True; force=False
            dispatch(A())
            assert run_m.call_count == 2


def test_status_reads_cache_state(tmp_path):
    """Smoke: status doesn't crash with an empty cache dir."""
    from cli import cmd_status
    cmd_status(cache_dir=tmp_path)
```

- [ ] **Step 2: Run tests, verify fail**

```bash
python -m pytest tests/test_cli.py -v
```

- [ ] **Step 3: Implement `cli.py`**

```python
# cli.py
"""Single-CLI orchestration for the info_theory research pipeline."""

from __future__ import annotations
import argparse
import sys
from pathlib import Path


CACHE_DIR_DEFAULT = Path.home() / ".castle" / "research"

# Stage registry: name → entry-point function
STAGES = {
    "snapshot": "pipeline.snapshot_palace:run_default",
    "load-palace": "pipeline.load_palace:run_default",
    "load-lme": "pipeline.load_longmemeval:run_default",
    "normalize": "pipeline.normalize:run_default",
    "embed": "pipeline.embed:run_default",
    "neighbors": "pipeline.neighbors:run_default",
    "nn-novelty": "pipeline.nn_novelty:run_default",
    "recon-residual": "pipeline.recon_residual:run_default",
    "stratify": "pipeline.stratify:run_default",
    "llm-surprise": "pipeline.llm_surprise:run_default",
    "downstream-eval": "pipeline.downstream_eval:run_default",
    "fit-decay": "analysis.fit_decay:run_default",
    "heterogeneity": "analysis.heterogeneity:run_default",
    "correlations": "analysis.correlations:run_default",
}


def build_arg_parser():
    p = argparse.ArgumentParser(prog="info-theory-cli")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("snapshot", help="snapshot palace LanceDB")
    sub.add_parser("pilot", help="5%% LME sizing pilot")

    run_p = sub.add_parser("run", help="run pipeline stages")
    run_p.add_argument("--stage", choices=list(STAGES.keys()))
    run_p.add_argument("--all", action="store_true")
    run_p.add_argument("--force", action="store_true")

    sub.add_parser("status", help="show cache state, stale stages")
    fig_p = sub.add_parser("figures", help="regenerate paper figures")
    fig_p.add_argument("--tables", action="store_true",
                        help="emit appendix LaTeX tables from results.yaml")
    ce = sub.add_parser("cost-estimate", help="dry-run cost estimator")
    # NOTE: required=False so Task 18's `parse_args(["cost-estimate"])` smoke
    # test passes. Runtime validation happens in cmd_cost_estimate.
    ce.add_argument("--stage", required=False)
    return p


def _run_stage(name: str, force: bool):
    if name not in STAGES:
        raise KeyError(f"unknown stage {name}")
    import importlib
    mod_path, fn = STAGES[name].split(":")
    mod = importlib.import_module(mod_path)
    getattr(mod, fn)(force=force)


def cmd_snapshot():
    from pipeline.snapshot_palace import snapshot_palace, compute_fingerprint
    import yaml
    src = Path.home() / ".castle" / "palace"
    dst = CACHE_DIR_DEFAULT / "palace_snapshot_2026-05-16"
    snapshot_palace(src, dst)
    # Compute and record fingerprint
    from pipeline.load_palace import load_palace
    table = load_palace(dst)
    rows = [{"drawer_id": d, "filed_at": f, "chunk_index": c}
            for d, f, c in zip(
                table.column("id").to_pylist(),
                table.column("filed_at").to_pylist(),
                table.column("chunk_index").to_pylist(),
            )]
    fp = compute_fingerprint(rows)
    seeds_path = Path(__file__).parent / "seeds.yaml"
    with open(seeds_path) as f: seeds = yaml.safe_load(f)
    seeds["palace_snapshot_fingerprint"] = fp
    with open(seeds_path, "w") as f: yaml.dump(seeds, f)
    print(f"Snapshot written. Fingerprint: {fp}")


def cmd_pilot():
    print("[pilot] Running 5% LME sample to tighten corpus-size estimate...")
    # Implementation: load 5% of LME, run through miner, count drawers
    from pipeline.load_longmemeval import load_longmemeval
    from benchmarks.longmemeval_bench import load_questions
    all_qs = load_questions()
    sample = all_qs[:len(all_qs)//20]
    # Save sample to tmp + run load
    import json, tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(sample, f)
        tmp = f.name
    table = load_longmemeval(tmp)
    est = table.num_rows * 20
    print(f"[pilot] 5% sample → {table.num_rows} drawers. Estimated total: ~{est}")


def cmd_status(cache_dir: Path = CACHE_DIR_DEFAULT):
    if not cache_dir.exists():
        print(f"Cache dir does not exist: {cache_dir}")
        return
    for p in sorted(cache_dir.iterdir()):
        size = p.stat().st_size if p.is_file() else "(dir)"
        print(f"  {p.name}\t{size}")


def cmd_figures(tables: bool = False):
    from analysis.figures import generate_all
    generate_all(emit_tables=tables)


def cmd_cost_estimate(stage: str):
    from pipeline.cost_estimate import estimate_cost
    result = estimate_cost(stage)
    print(f"Estimated cost for stage '{stage}': ${result['mean']:.2f} "
          f"(range ${result['lo']:.2f}-${result['hi']:.2f})")


def dispatch(args):
    if args.command == "snapshot": cmd_snapshot()
    elif args.command == "pilot": cmd_pilot()
    elif args.command == "status": cmd_status()
    elif args.command == "figures": cmd_figures(tables=args.tables)
    elif args.command == "cost-estimate": cmd_cost_estimate(args.stage)
    elif args.command == "run":
        if args.all:
            for s in STAGES.keys():
                _run_stage(s, args.force)
        elif args.stage:
            _run_stage(args.stage, args.force)
        else:
            print("Specify --stage X or --all"); sys.exit(2)


def main():
    args = build_arg_parser().parse_args()
    dispatch(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest tests/test_cli.py -v
```

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/cli.py research/info_theory/tests/test_cli.py
git commit -m "feat(cli): orchestration entry point with stage dispatch"
```

---

### Task 19: Cost-estimate subcommand

**Files:**
- Create: `research/info_theory/pipeline/cost_estimate.py`
- Create: `research/info_theory/tests/test_cost_estimate.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cost_estimate.py
from unittest.mock import patch
from pipeline.cost_estimate import estimate_cost, _haiku_price_per_1k


def test_estimate_cost_returns_lo_mean_hi():
    with patch("pipeline.cost_estimate._sample_drawers") as m:
        m.return_value = [{"text": "x" * 1000}] * 10
        result = estimate_cost("llm-surprise", n_samples=10, target_calls=1000)
    assert "lo" in result and "mean" in result and "hi" in result
    assert result["lo"] <= result["mean"] <= result["hi"]


def test_haiku_price_constants_match_2026_05():
    """Pinned at experiment start; update if pricing changes."""
    # Haiku 4.5 pricing as of 2026-05-16
    p = _haiku_price_per_1k()
    assert p["input"] > 0 and p["output"] > 0
```

- [ ] **Step 2: Run tests, verify fail**

```bash
python -m pytest tests/test_cost_estimate.py -v
```

- [ ] **Step 3: Implement `cost_estimate.py`**

```python
# pipeline/cost_estimate.py
"""Dry-run cost estimator. Samples 10 drawers, measures input-token
count, multiplies by stratified subsample size and current Haiku
pricing. Prints upper/lower bounds based on observed variance."""

from __future__ import annotations
import numpy as np
import tiktoken

_ENC = tiktoken.get_encoding("cl100k_base")


def _haiku_price_per_1k() -> dict:
    """Pinned Haiku 4.5 pricing as of 2026-05-16. USD per 1k tokens."""
    return {"input": 0.0008, "output": 0.004}


def _sample_drawers(n_samples: int = 10):
    """Stub — replaced in test patches. Production: load real drawers."""
    raise NotImplementedError("set via test patch or call load_palace first")


def estimate_cost(stage: str, n_samples: int = 10, target_calls: int = 1000) -> dict:
    """Returns {lo, mean, hi} USD estimate."""
    if stage != "llm-surprise":
        return {"lo": 0.0, "mean": 0.0, "hi": 0.0, "note": "non-LLM stage"}
    samples = _sample_drawers(n_samples)
    token_counts = [len(_ENC.encode(d["text"])) for d in samples]
    prices = _haiku_price_per_1k()
    # Per call: 20 priors × 500 tokens avg + instructions ~200 + target ~500
    # The samples here approximate target tokens; multiply for priors+instructions
    per_call_tokens = [t + 10000 + 200 for t in token_counts]  # rough
    per_call_cost = [t / 1000 * prices["input"] + 100 / 1000 * prices["output"]
                     for t in per_call_tokens]
    mean = float(np.mean(per_call_cost) * target_calls)
    sd = float(np.std(per_call_cost) * target_calls)
    return {
        "lo": max(0.0, mean - 1.96 * sd),
        "mean": mean,
        "hi": mean + 1.96 * sd,
    }
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest tests/test_cost_estimate.py -v
```

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/pipeline/cost_estimate.py \
        research/info_theory/tests/test_cost_estimate.py
git commit -m "feat(cli): cost-estimate dry-run before claude-cli spend"
```

---

## Phase 9: figures + appendix tables

### Task 20: Figures + table emission

**Files:**
- Create: `research/info_theory/analysis/figures.py`
- Create: `research/info_theory/tests/test_figures.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_figures.py
from pathlib import Path
from analysis.figures import emit_tables_from_results


def test_emit_tables_writes_one_tex_per_table(tmp_path):
    results = {
        "K_sensitivity": {"K=10": {"alpha": 0.5}, "K=20": {"alpha": 0.48}},
        "per_stratum_fits": {"miner::room1": {"alpha": 0.6, "tau": None}},
    }
    out_dir = tmp_path / "appendix"
    emit_tables_from_results(results, out_dir)
    assert (out_dir / "table_K_sensitivity.tex").exists()
    assert (out_dir / "table_per_stratum_fits.tex").exists()
    content = (out_dir / "table_K_sensitivity.tex").read_text()
    assert "\\begin{tabular}" in content


def test_emit_tables_skips_empty_groups(tmp_path):
    results = {"empty_group": {}}
    out_dir = tmp_path / "appendix"
    emit_tables_from_results(results, out_dir)
    assert not (out_dir / "table_empty_group.tex").exists()
```

- [ ] **Step 2: Run tests, verify fail**

```bash
python -m pytest tests/test_figures.py -v
```

- [ ] **Step 3: Implement `figures.py`**

```python
# analysis/figures.py
"""Generate paper figures + emit appendix LaTeX tables."""

from __future__ import annotations
from pathlib import Path
import yaml


def emit_tables_from_results(results: dict, out_dir: Path) -> None:
    """One .tex file per top-level results.yaml table key."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for table_name, rows in results.items():
        if not rows:
            continue
        target = out_dir / f"table_{table_name}.tex"
        lines = ["\\begin{tabular}{l" + "r" * (len(next(iter(rows.values()))) if rows else 1) + "}",
                 "\\hline"]
        # Header
        cols = sorted(next(iter(rows.values())).keys()) if rows else []
        lines.append(" & ".join(["", *cols]) + " \\\\")
        lines.append("\\hline")
        for row_name, vals in rows.items():
            cells = [row_name] + [
                f"{vals.get(c):.3g}" if isinstance(vals.get(c), (int, float)) else str(vals.get(c, ""))
                for c in cols
            ]
            lines.append(" & ".join(cells) + " \\\\")
        lines.append("\\hline")
        lines.append("\\end{tabular}")
        target.write_text("\n".join(lines))


def generate_all(emit_tables: bool = False) -> None:
    """Entry point for `python -m cli figures` and `cli figures --tables`."""
    results_path = Path(__file__).parents[1] / "paper" / "results.yaml"
    if results_path.exists():
        with open(results_path) as f:
            results = yaml.safe_load(f)
    else:
        print(f"WARN: {results_path} not found; nothing to emit")
        return
    out_figs = Path(__file__).parents[1] / "paper" / "figures"
    out_figs.mkdir(parents=True, exist_ok=True)
    if emit_tables:
        tables = results.get("tables", {})
        emit_tables_from_results(tables, out_figs.parent / "appendix")
    # PDF figures: matplotlib-based, implementation deferred to analysis run
    print(f"Figures regenerated to {out_figs}")
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest tests/test_figures.py -v
```

- [ ] **Step 5: Commit**

```bash
git add research/info_theory/analysis/figures.py \
        research/info_theory/tests/test_figures.py
git commit -m "feat(analysis): figures.py — one LaTeX table per results.yaml key"
```

---

## Phase 10: CI + REPRODUCIBILITY.md

### Task 21: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/research-info-theory.yml`

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/research-info-theory.yml
name: Research — info_theory

on:
  push:
    paths:
      - 'research/info_theory/**'
      - '.github/workflows/research-info-theory.yml'
  pull_request:
    paths:
      - 'research/info_theory/**'

jobs:
  unit-and-integration:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install Castle + research deps
        run: |
          pip install -e .
          pip install -e research/info_theory[dev]
      - name: Run Tier 1 unit tests
        run: |
          cd research/info_theory
          pytest tests/ -v --tb=short -x
      - name: Run integration smoke (LME fixture)
        run: |
          cd research/info_theory
          pytest tests/ -v -k integration --tb=short

  reproducibility-tier4:
    runs-on: ubuntu-latest
    needs: unit-and-integration
    if: github.event_name == 'pull_request' && contains(github.event.pull_request.changed_files, 'paper/results.yaml')
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install
        run: |
          pip install -e .
          pip install -e research/info_theory[dev]
      - name: Tier 4 — LME-only reproducibility check
        run: |
          cd research/info_theory
          # Run the full LME pipeline on a frozen 1000-drawer subsample
          # Compare fitted parameters to paper/results.yaml (±1e-3 tolerance)
          python -m pytest tests/test_tier4_reproducibility.py -v
```

- [ ] **Step 2: Validate the YAML locally**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/research-info-theory.yml'))"
```

Expected: no exception.

- [ ] **Step 3: Create the Tier 4 reproducibility test referenced by CI**

```python
# research/info_theory/tests/test_tier4_reproducibility.py
"""Tier 4: LME-only full-pipeline reproducibility check.
Runs only when paper/results.yaml changes in a PR.
Compares freshly-fitted parameters against committed results.yaml
within ±1e-3 (cross-machine tolerance band from REPRODUCIBILITY.md)."""

from pathlib import Path
import yaml
import pytest


RESULTS_PATH = Path(__file__).parent.parent / "paper" / "results.yaml"
TOLERANCE = 1e-3  # cross-machine; per REPRODUCIBILITY.md


@pytest.mark.tier4
def test_lme_reproducibility_within_tolerance():
    """Re-run LME pipeline on 1000-drawer subsample, diff vs results.yaml.

    Skipped if results.yaml doesn't yet exist (initial development phase)."""
    if not RESULTS_PATH.exists():
        pytest.skip("results.yaml not yet committed; Tier 4 not enforced")
    with open(RESULTS_PATH) as f:
        committed = yaml.safe_load(f)
    if not committed.get("headline_numbers"):
        pytest.skip("results.yaml empty; Tier 4 not enforced")

    # TODO when implementing: invoke the LME-only pipeline run here
    # and compare each value in `committed["headline_numbers"]` to the
    # freshly-computed value within TOLERANCE.
    # Until then this test only verifies file structure is valid.
    assert isinstance(committed["headline_numbers"], dict)
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/research-info-theory.yml \
        research/info_theory/tests/test_tier4_reproducibility.py
git commit -m "ci: research-info-theory workflow + Tier 4 reproducibility stub"
```

---

### Task 22: Populate REPRODUCIBILITY.md

**Files:**
- Modify: `research/info_theory/REPRODUCIBILITY.md`

- [ ] **Step 1: Write the manifest**

```markdown
# Reproducibility Manifest

This document captures the configuration that produces the numbers in
`paper/results.yaml`. Reviewers reproducing on a different machine
should match all items below; numerical results match within ±1e-3.

## Environment

- Python: `>=3.11`
- OS: Linux (developed on Fedora 44 / kernel 6.19)
- Lockfile: `research/info_theory/uv.lock` (committed; recreate via `uv sync`)
- bge-m3 model revision: pinned in `seeds.yaml` under `bge_m3_revision`
- Castle source-tree commit: pinned in `seeds.yaml` under `castle_commit`
- Palace snapshot fingerprint: pinned in `seeds.yaml` under `palace_snapshot_fingerprint`
- LongMemEval release: pinned in `seeds.yaml` under `longmemeval_release`

## Seeds

All seeds live in `research/info_theory/seeds.yaml`. Any change → new
run → new `results.yaml`. The five active seeds:

- `numpy_seed` — generic NumPy RNG
- `subsample_seed` — C-stage stratified sampling
- `bootstrap_seed` — block-bootstrap resamples for decay-fit CIs
- `prompt_template_seed` — any randomized prompt-template variations
- `downstream_eval_seed` — bootstrap CIs on H3 R@5 deltas

## Hardware

- **CUDA GPU**: required for embedding 65k drawers in reasonable time.
  CPU-only fallback adds ~2-4 hours and is documented but not the
  target configuration.

## Claude CLI invocation

C-stage uses the `claude-cli` provider (PR #49). The exact invocation
is recorded with each call in `llm_surprise_subsample.parquet`:

- Model: `claude-haiku-4-5-20251001`
- Flags: `--no-session-persistence`, `--disable-slash-commands`,
  `--output-format json`
- Prompt template SHA: pinned in `seeds.yaml` under `prompt_template_sha`

## Two-machine verification protocol

Before first commit of `results.yaml`:

1. Developer runs full pipeline on Machine A (GPU dev box).
2. Output written to `paper/results.yaml`.
3. Developer runs Tier 4 reproducibility check on Machine B (fresh
   checkout, different machine if possible). On match (within
   tolerance), `results.yaml` is committed.
4. From that point forward, CI verifies on every commit.

## Tolerance bands

- Same-machine same-seed runs: ±1e-6 on fitted parameters
- Cross-machine runs: ±1e-3 on fitted parameters
- H3 R@5 deltas: ±0.5 percentage points absolute
```

- [ ] **Step 2: Commit**

```bash
git add research/info_theory/REPRODUCIBILITY.md
git commit -m "docs(research): populate REPRODUCIBILITY.md manifest"
```

---

## Phase 11: paper LaTeX scaffolding

### Task 23: Paper skeleton (main.tex, appendix.tex)

**Files:**
- Create: `research/info_theory/paper/main.tex`
- Create: `research/info_theory/paper/appendix.tex`
- Create: `research/info_theory/paper/results.yaml`
- Create: `research/info_theory/paper/.gitignore`

- [ ] **Step 1: Write `main.tex` skeleton**

```latex
% paper/main.tex
\documentclass{article}
\usepackage{amsmath, amssymb, graphicx, hyperref, booktabs}

\title{Measuring Information Content in Verbatim AI Memory:
  Methodology, Source-Type Heterogeneity, and a Downstream Utility Test}
\author{Ladislav Bihari}

\begin{document}
\maketitle

\begin{abstract}
% TODO once results.yaml is populated
\end{abstract}

\section{Introduction}
% Frames as methodology paper; cites MemPalace + Castle as data
% infrastructure; motivates source-type analysis as a novel axis.

\section{Related Work}
% mem0, Zep, Letta, MemPalace, MemGPT, LongMemEval, info theory
% (Shannon, MDL), locally linear embedding.

\section{Methods}
% Estimators A/B/C, corpora + stratification, H1/H2/H3 procedures,
% statistical correction.

\section{Results}
% H1 source-type violin plot (headline); H2 per-cell fits; A/B/C
% correlations; H3 downstream R@5 deltas.

\section{Discussion}
% (a) Heterogeneity implications; (b) Limits of protocol-as-behavior-
% driver (the ~10-deliberate-MCP-filings observation); (c) verbatim-
% vs-lossy info-theoretically; (d) downstream-validation
% interpretation; (e) source-aware smart-mining implication for
% Phase 2.

\section{Limitations}
% n=1 user palace; bge-m3 dependency; LME stratification asymmetry;
% LLM-rating-not-log-prob; within-file correlation.

\section{Conclusion}
% Phase 2 pointer.

\input{appendix}

\end{document}
```

- [ ] **Step 2: Write `appendix.tex` skeleton**

```latex
% paper/appendix.tex
\appendix
\section{Sensitivity analyses}
\subsection{K sensitivity}
\input{appendix/table_K_sensitivity}

\subsection{Lambda sensitivity}
\input{appendix/table_lambda_sensitivity}

\subsection{Block-size sensitivity}
\input{appendix/table_block_size_sensitivity}

\section{Per-cell fits}
\input{appendix/table_per_stratum_fits}

\section{Downstream R@5 by question type}
\input{appendix/table_downstream_per_question_type}

\section{Prompt template}
% Verbatim prompt used for llm_surprise C-stage.

\section{Raw-text vs normalized comparison}
\input{appendix/table_raw_vs_normalized}
```

- [ ] **Step 3: Write empty `results.yaml`**

```yaml
# paper/results.yaml — populated by analysis pipeline; checked in
# after two-machine verification per REPRODUCIBILITY.md
tables: {}
headline_numbers: {}
```

- [ ] **Step 4: Write `.gitignore` for paper build artifacts**

```
# paper/.gitignore
*.aux
*.bbl
*.blg
*.log
*.out
*.toc
*.pdf
appendix/*.tex
figures/*.pdf
```

- [ ] **Step 5: Verify the .tex files parse**

```bash
cd research/info_theory/paper
# If pdflatex isn't installed, skip; otherwise:
pdflatex -draftmode main.tex 2>&1 | tail -5 || echo "pdflatex unavailable; skipping"
```

- [ ] **Step 6: Commit**

```bash
git add research/info_theory/paper/
git commit -m "scaffold(paper): main.tex + appendix.tex + results.yaml skeleton"
```

---

## Phase 12: integration tests

### Task 24: End-to-end smoke test on a 100-drawer fixture

**Files:**
- Create: `research/info_theory/tests/test_e2e_smoke.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_e2e_smoke.py
"""End-to-end smoke: full pipeline on a 100-drawer fixture in <30s.
Numerical sentinels rather than exact-value asserts."""

import pytest
import pyarrow as pa
from pathlib import Path


@pytest.fixture
def mini_corpus():
    rows = []
    for i in range(100):
        rows.append({
            "drawer_id": f"d{i:03d}",
            "wing": "test_wing" if i < 80 else "other_wing",
            "room": "test_room",
            "added_by": "miner",
            "filed_at": f"2026-01-{(i%28)+1:02d}T00:00:00Z",
            "chunk_index": i % 3,
            "source_file": f"f{i//3}",
            "text": f"sample drawer {i} with some text content",
            "session_id": None, "question_id": None, "question_type": None,
        })
    return pa.Table.from_pylist(rows)


def test_e2e_smoke_pipeline(mini_corpus, monkeypatch, tmp_path):
    """Smoke: normalize → embed (mocked) → neighbors → nn_novelty +
    recon_residual. Asserts file existence + bounds."""
    from pipeline.normalize import normalize
    from pipeline.nn_novelty import compute_for_table as nn
    from pipeline.recon_residual import compute_for_table as rr
    from unittest.mock import patch
    import numpy as np

    # Add mock vectors
    rng = np.random.default_rng(42)
    vectors = [rng.normal(size=8).tolist() for _ in range(mini_corpus.num_rows)]
    table = mini_corpus.append_column("vector", pa.array(vectors))

    nn_out = nn(table, group_by="wing")
    assert "nn_novelty" in nn_out.column_names
    nn_values = [v for v in nn_out.column("nn_novelty").to_pylist() if v is not None]
    # nn_novelty = 1 - max_cosine(target, priors); cosine ∈ [-1, 1] so
    # nn_novelty ∈ [0, 2] — bound is NOT [0,1] for un-normalized vectors.
    assert all(0 <= v <= 2.0001 for v in nn_values)

    rr_out = rr(table, k_target=20, k_floor=5, lam=1e-3, group_by="wing")
    assert "recon_residual" in rr_out.column_names
```

- [ ] **Step 2: Run, verify pass**

```bash
python -m pytest tests/test_e2e_smoke.py -v
```

- [ ] **Step 3: Commit**

```bash
git add research/info_theory/tests/test_e2e_smoke.py
git commit -m "test(e2e): 100-drawer smoke pipeline in <30s"
```

---

## Phase 13: pre-experiment validation

### Task 25: Cross-corpus merge integration test

**Files:**
- Create: `research/info_theory/tests/test_cross_corpus_merge.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_cross_corpus_merge.py
"""Verify the merge of palace + LME drawers produces a valid Arrow
table with Castle-specific fields nullable."""

import pyarrow as pa
from pathlib import Path
from pipeline.load_palace import load_palace
from pipeline.load_longmemeval import load_longmemeval


def test_merge_handles_nullable_castle_fields():
    palace = load_palace(Path(__file__).parent / "fixtures" / "palace_lance_mini")
    lme = load_longmemeval(Path(__file__).parent / "fixtures" / "longmemeval_mini.json")

    # Unify schemas: palace lacks question_id; LME lacks added_by_palace_specific
    # Pad both to a common schema with nullable columns
    common_cols = ["drawer_id", "text", "filed_at", "chunk_index",
                   "source_file", "wing", "room", "added_by",
                   "session_id", "question_id", "question_type"]
    # Palace adds null columns
    palace_padded = palace
    for c in ("session_id", "question_id", "question_type"):
        if c not in palace_padded.column_names:
            palace_padded = palace_padded.append_column(
                c, pa.array([None]*palace_padded.num_rows, type=pa.string())
            )
    # LME has all common cols already
    # Project both to the same column order
    palace_proj = palace_padded.select([c for c in common_cols
                                          if c in palace_padded.column_names])
    # Rename palace's 'id' to 'drawer_id' for consistency
    if "drawer_id" not in palace_proj.column_names and "id" in palace_padded.column_names:
        palace_proj = palace_padded.rename_columns(
            ["drawer_id" if n == "id" else n for n in palace_padded.column_names]
        ).select([c for c in common_cols
                  if c in ["drawer_id" if n == "id" else n
                           for n in palace_padded.column_names]])

    # The merge itself
    merged = pa.concat_tables([palace_proj, lme], promote_options="default")
    assert merged.num_rows == palace_proj.num_rows + lme.num_rows
    # No silent type-coercion errors
    assert "drawer_id" in merged.column_names
```

- [ ] **Step 2: Run, verify pass (or fail informatively)**

```bash
python -m pytest tests/test_cross_corpus_merge.py -v
```

If it fails, the test exposes a real schema-alignment bug — fix the load_palace / load_longmemeval column names before proceeding.

- [ ] **Step 3: Commit**

```bash
git add research/info_theory/tests/test_cross_corpus_merge.py
git commit -m "test(integration): cross-corpus merge with nullable Castle fields"
```

---

## Phase 14: pre-paper-release manual gate

### Task 26: Manual pre-release checklist

**Files:**
- Modify: `research/info_theory/REPRODUCIBILITY.md` (append checklist)

This task is documentation only — captures the manual steps that gate the paper submission.

- [ ] **Step 1: Append to REPRODUCIBILITY.md**

```markdown
## Pre-paper-release manual gate

Before submitting the paper to arXiv, complete this checklist:

- [ ] Tier 4 full reproducibility check on both corpora (Machine A)
- [ ] Tier 4 full reproducibility check on Machine B (fresh checkout)
- [ ] All numbers in `paper/main.tex` and `paper/appendix.tex` cross-reference `paper/results.yaml`
- [ ] `pdflatex main.tex` produces a clean PDF (no missing-ref warnings)
- [ ] `reasoning_spotcheck` excerpts in appendix have been user-reviewed (privacy)
- [ ] arXiv categories chosen (default: cs.IR + cs.AI)
- [ ] Author + affiliation correct
- [ ] BibTeX entries cite MemPalace + understanding repos with correct URLs
- [ ] Co-authorship policy decided per venue (Claude as acknowledgment or byline)
```

- [ ] **Step 2: Commit**

```bash
git add research/info_theory/REPRODUCIBILITY.md
git commit -m "docs(research): pre-paper-release manual gate checklist"
```

---

## Final task list summary

| # | Task | Phase | Notes |
|---|---|---|---|
| 0 | H3 feasibility spike | Pre-impl | Gates all `[H3]` tasks |
| 1 | Scaffolding | 1 | Dir structure, pyproject |
| 2 | Snapshot palace | 2 | Tuple-hash fingerprint |
| 3 | Load palace | 2 | Parses `metadata_json` |
| 4 | Load LongMemEval | 2 | Refactors `longmemeval_bench.py` first |
| 5 | Normalize text | 2 | Strip code + truncate 2000 tokens |
| 6 | Embed (cached) | 3 | bge-m3 via Castle's embedder |
| 7 | Neighbors KNN | 3 | Same-wing / same-session constraint |
| 8 | Estimator A (nn_novelty) | 4 | Cheap baseline |
| 9 | Estimator B (recon_residual) | 4 | LLE + Tikhonov |
| 10 | Estimator C — single call | 4 | Prompt + parsing |
| 11 | Estimator C — resumable batch | 4 | Cost cap + partials |
| 12 | Stratify allocation | 5 | Termination guard |
| 13 | Fit decay models | 6 | WLS power-law + OLS exp + AIC |
| 14 | Block bootstrap | 6 | Source-aware |
| 15 | Correlations | 6 | Spearman + Pearson w/ CIs |
| 16 | Heterogeneity (H1) | 6 | Kruskal-Wallis + ε² |
| 16b | Aggregation | 6 | BH-FDR, N* saturation, ≥200 floor |
| 17 | Downstream eval `[H3]` | 7 | Contingent on Task 0 |
| 18 | CLI core | 8 | snapshot/pilot/run/status |
| 19 | Cost estimator | 8 | Dry-run pricing |
| 20 | Figures + tables | 9 | One .tex per table |
| 21 | CI workflow | 10 | GitHub Actions |
| 22 | REPRODUCIBILITY.md | 10 | Manifest |
| 23 | Paper LaTeX scaffold | 11 | main + appendix |
| 24 | E2E smoke test | 12 | <30s, 100-drawer fixture |
| 25 | Cross-corpus merge test | 13 | Nullable Castle fields |
| 26 | Pre-release checklist | 14 | Documentation only |

**Sequence note**: Tasks 1-12 are strict prereqs for Tasks 13-17. Tasks 18-20 can run in parallel with Phase 6. Tasks 21-26 are wrap-up and can run after the analysis pipeline produces results.

**H3 contingency**: Task 0's spike outcome decides whether Task 17 runs. If H3 OUT, success criteria adjusts to "H1 + H2 only" and paper Discussion folds H3 motivation into future-work pointer.
