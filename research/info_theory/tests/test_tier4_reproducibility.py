"""Tier 4: LME-only full-pipeline reproducibility check.
Runs only when paper/results.yaml changes in a PR.
Compares freshly-fitted parameters against committed results.yaml
within ±1e-3 (cross-machine tolerance band from REPRODUCIBILITY.md)."""

from pathlib import Path

import pytest
import yaml

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
