import time

import pyarrow as pa

from pipeline.neighbors import compute_all_neighbors, find_neighbors


def _table_with_vectors(n=10, dim=4):
    return pa.table(
        {
            "drawer_id": [f"d{i}" for i in range(n)],
            "wing": ["w"] * n,
            "filed_at": [f"2026-01-{i + 1:02d}" for i in range(n)],
            "chunk_index": [0] * n,
            "source_file": [f"f{i}" for i in range(n)],
            "vector": [[float(i + j) for j in range(dim)] for i in range(n)],
        }
    )


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
        {
            "drawer_id": "d0",
            "wing": "w",
            "filed_at": "2026-01-01",
            "chunk_index": 0,
            "source_file": "f",
            "vector": [1.0, 0.0],
        },
        {
            "drawer_id": "d1",
            "wing": "w",
            "filed_at": "2026-01-02",
            "chunk_index": 0,
            "source_file": "f",
            "vector": [0.0, 1.0],
        },
        {
            "drawer_id": "target",
            "wing": "w",
            "filed_at": "2026-01-03",
            "chunk_index": 0,
            "source_file": "f",
            "vector": [1.0, 0.01],
        },
    ]
    t = pa.Table.from_pylist(rows)
    neighbors = find_neighbors(t, target_idx=2, k=1, prior_filter="filed_at")
    assert neighbors == [0]  # d0 is closest


def test_find_neighbors_same_wing_constraint_palace():
    rows = [
        {
            "drawer_id": "a",
            "wing": "w1",
            "filed_at": "2026-01-01",
            "chunk_index": 0,
            "source_file": "f",
            "vector": [1.0, 0.0],
        },
        {
            "drawer_id": "b",
            "wing": "w2",
            "filed_at": "2026-01-02",
            "chunk_index": 0,
            "source_file": "f",
            "vector": [1.0, 0.0],
        },
        {
            "drawer_id": "c",
            "wing": "w1",
            "filed_at": "2026-01-03",
            "chunk_index": 0,
            "source_file": "f",
            "vector": [0.5, 0.5],
        },
    ]
    t = pa.Table.from_pylist(rows)
    # target=c in w1; b is in w2 and should be excluded
    neighbors = find_neighbors(t, target_idx=2, k=10, prior_filter="filed_at", group_by="wing")
    assert neighbors == [0]  # only 'a' is in same wing


def test_compute_all_neighbors_matches_find_neighbors_single():
    """Batch computation must match per-row computation for every row."""
    t = _table_with_vectors(20, dim=6)
    all_nbrs = compute_all_neighbors(t, k=3, prior_filter="filed_at")
    for i in range(t.num_rows):
        assert all_nbrs[i] == find_neighbors(t, target_idx=i, k=3, prior_filter="filed_at")


def test_compute_all_neighbors_empty_for_first_row_per_group():
    """The earliest row in each group has no priors and must return []."""
    rows = [
        {
            "drawer_id": "a0",
            "wing": "w1",
            "filed_at": "2026-01-01",
            "vector": [1.0, 0.0],
        },
        {
            "drawer_id": "a1",
            "wing": "w1",
            "filed_at": "2026-01-02",
            "vector": [0.9, 0.1],
        },
        {
            "drawer_id": "b0",
            "wing": "w2",
            "filed_at": "2026-01-03",
            "vector": [0.0, 1.0],
        },
        {
            "drawer_id": "b1",
            "wing": "w2",
            "filed_at": "2026-01-04",
            "vector": [0.1, 0.9],
        },
    ]
    t = pa.Table.from_pylist(rows)
    all_nbrs = compute_all_neighbors(t, k=5, prior_filter="filed_at", group_by="wing")
    # Row 0 is the earliest in w1 -> no priors
    assert all_nbrs[0] == []
    # Row 2 is the earliest in w2 -> no priors even though rows 0 and 1 predate it
    assert all_nbrs[2] == []
    # Row 1 in w1 has row 0 as prior
    assert all_nbrs[1] == [0]
    # Row 3 in w2 has row 2 as prior (row 0/1 excluded by group_by)
    assert all_nbrs[3] == [2]


def test_compute_all_neighbors_speedup_over_naive():
    """Batch call should be strictly faster than N per-row `find_neighbors` calls."""
    t = _table_with_vectors(200, dim=32)

    t0 = time.perf_counter()
    batch = compute_all_neighbors(t, k=5, prior_filter="filed_at")
    batch_elapsed = time.perf_counter() - t0

    t0 = time.perf_counter()
    naive = [
        find_neighbors(t, target_idx=i, k=5, prior_filter="filed_at") for i in range(t.num_rows)
    ]
    naive_elapsed = time.perf_counter() - t0

    assert batch == naive
    assert batch_elapsed < naive_elapsed, (
        f"batch {batch_elapsed:.3f}s not faster than naive {naive_elapsed:.3f}s"
    )
