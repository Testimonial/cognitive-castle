import pyarrow as pa

from pipeline.neighbors import find_neighbors


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
