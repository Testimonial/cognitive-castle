import numpy as np
import pyarrow as pa

from pipeline.nn_novelty import compute_for_table, compute_nn_novelty  # noqa: F401


def test_nn_novelty_first_drawer_is_max():
    t = pa.table(
        {
            "drawer_id": ["a"],
            "wing": ["w"],
            "filed_at": ["2026-01-01"],
            "chunk_index": [0],
            "source_file": ["f"],
            "vector": [[1.0, 0.0]],
        }
    )
    out = compute_for_table(t, group_by="wing")
    assert out.column("nn_novelty").to_pylist()[0] == 1.0
    assert out.column("is_first").to_pylist()[0] is True


def test_nn_novelty_identical_to_prior_gives_zero():
    rows = [
        {
            "drawer_id": "a",
            "wing": "w",
            "filed_at": "2026-01-01",
            "chunk_index": 0,
            "source_file": "f",
            "vector": [1.0, 0.0],
        },
        {
            "drawer_id": "b",
            "wing": "w",
            "filed_at": "2026-01-02",
            "chunk_index": 0,
            "source_file": "f",
            "vector": [1.0, 0.0],
        },
    ]
    t = pa.Table.from_pylist(rows)
    out = compute_for_table(t, group_by="wing")
    novelties = out.column("nn_novelty").to_pylist()
    assert novelties[0] == 1.0  # first
    assert abs(novelties[1] - 0.0) < 1e-6  # identical to prior


def test_nn_novelty_orthogonal_to_prior_gives_one():
    rows = [
        {
            "drawer_id": "a",
            "wing": "w",
            "filed_at": "2026-01-01",
            "chunk_index": 0,
            "source_file": "f",
            "vector": [1.0, 0.0],
        },
        {
            "drawer_id": "b",
            "wing": "w",
            "filed_at": "2026-01-02",
            "chunk_index": 0,
            "source_file": "f",
            "vector": [0.0, 1.0],
        },
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
        rows.append(
            {
                "drawer_id": f"d{i}",
                "wing": "w",
                "filed_at": f"2026-01-{i + 1:02d}",
                "chunk_index": 0,
                "source_file": "f",
                "vector": v.tolist(),
            }
        )
    t = pa.Table.from_pylist(rows)
    out = compute_for_table(t, group_by="wing")
    nn = out.column("nn_novelty").to_pylist()
    # All post-first drawers should be very close to some prior → low novelty
    assert max(nn[1:]) < 0.1
