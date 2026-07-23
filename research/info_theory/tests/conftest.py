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
