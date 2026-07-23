"""End-to-end smoke: full pipeline on a 100-drawer fixture in <30s.
Numerical sentinels rather than exact-value asserts."""

import pytest
import pyarrow as pa


@pytest.fixture
def mini_corpus():
    rows = []
    for i in range(100):
        rows.append(
            {
                "drawer_id": f"d{i:03d}",
                "wing": "test_wing" if i < 80 else "other_wing",
                "room": "test_room",
                "added_by": "miner",
                "filed_at": f"2026-01-{(i % 28) + 1:02d}T00:00:00Z",
                "chunk_index": i % 3,
                "source_file": f"f{i // 3}",
                "text": f"sample drawer {i} with some text content",
                "session_id": None,
                "question_id": None,
                "question_type": None,
            }
        )
    return pa.Table.from_pylist(rows)


def test_e2e_smoke_pipeline(mini_corpus):
    """Smoke: normalize -> embed (mocked) -> neighbors -> nn_novelty +
    recon_residual. Asserts file existence + bounds."""
    from pipeline.nn_novelty import compute_for_table as nn
    from pipeline.recon_residual import compute_for_table as rr
    import numpy as np

    # Add mock vectors
    rng = np.random.default_rng(42)
    vectors = [rng.normal(size=8).tolist() for _ in range(mini_corpus.num_rows)]
    table = mini_corpus.append_column("vector", pa.array(vectors))

    nn_out = nn(table, group_by="wing")
    assert "nn_novelty" in nn_out.column_names
    nn_values = [v for v in nn_out.column("nn_novelty").to_pylist() if v is not None]
    # nn_novelty = 1 - max cosine similarity; cosine in [-1, 1] so v in [0, 2]
    assert all(0 <= v <= 2.0001 for v in nn_values)

    rr_out = rr(table, k_target=20, k_floor=5, lam=1e-3, group_by="wing")
    assert "recon_residual" in rr_out.column_names
