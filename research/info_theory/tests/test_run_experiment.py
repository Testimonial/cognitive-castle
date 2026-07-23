"""Driver-level tests for run_experiment.py.

Every stage is monkey-patched — we never hit the real palace, embedder,
or LLM. We only verify that (a) the config has sensible defaults,
(b) LME/H3 branches are skipped when ``lme_source`` is None, and
(c) ``paper/results.yaml`` is written and parses as valid YAML.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pyarrow as pa
import yaml

import run_experiment


# ---------------------------------------------------------------------------
# Fixtures — tiny fake tables that satisfy the code paths
# ---------------------------------------------------------------------------


def _fake_palace_table() -> pa.Table:
    rows = [
        {
            "drawer_id": f"d{i:03d}",
            "text": f"text {i}",
            "filed_at": f"2026-01-{(i % 27) + 1:02d}T00:00:00Z",
            "chunk_index": i % 3,
            "wing": "wing_a" if i < 6 else "wing_b",
            "added_by": "miner",
            "metadata_json": "{}",
        }
        for i in range(10)
    ]
    return pa.Table.from_pylist(rows)


def _fake_estimator_table_a() -> pa.Table:
    table = _fake_palace_table()
    novelties = [0.1 * i for i in range(table.num_rows)]
    is_first = [False] * table.num_rows
    table = table.append_column("nn_novelty", pa.array(novelties, type=pa.float64()))
    table = table.append_column("is_first", pa.array(is_first, type=pa.bool_()))
    return table


def _fake_estimator_table_b() -> pa.Table:
    table = _fake_palace_table()
    residuals = [0.2 * i for i in range(table.num_rows)]
    return table.append_column("recon_residual", pa.array(residuals, type=pa.float64()))


# ---------------------------------------------------------------------------
# 1. Config defaults sanity
# ---------------------------------------------------------------------------


def test_config_defaults_are_sensible():
    cfg = run_experiment.Config()

    assert cfg.subsample_n > 0
    assert cfg.subsample_floor > 0
    assert cfg.subsample_floor <= cfg.subsample_n
    assert cfg.max_cost_usd > 0
    assert cfg.n_bootstrap > 0
    assert cfg.seed >= 0
    assert cfg.merge_every > 0
    assert cfg.run_c_stage is True
    assert cfg.run_h3 is True
    assert cfg.force is False
    assert cfg.lme_source is None
    assert isinstance(cfg.palace_src, Path)
    assert isinstance(cfg.cache_dir, Path)
    # llm defaults are strings
    assert isinstance(cfg.llm_provider_name, str) and cfg.llm_provider_name
    assert isinstance(cfg.llm_model, str) and cfg.llm_model


# ---------------------------------------------------------------------------
# 2. LME-none skips H3
# ---------------------------------------------------------------------------


def _patch_all_stages(monkeypatch, tmp_path, *, lme_source):
    """Install mocks for every heavy stage. Returns a bag of MagicMocks."""
    mocks = MagicMock()

    # snapshot / load palace
    def fake_snapshot(config):
        d = Path(config.cache_dir) / "palace_snapshot"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def fake_load_palace(config, snap):
        return _fake_palace_table()

    def fake_load_lme(config):
        if config.lme_source is None:
            return None
        return _fake_palace_table()  # shape doesn't matter for these tests

    def fake_normalize(config, table):
        return table

    def fake_embed(config, table):
        vecs = [[0.0, 1.0] for _ in range(table.num_rows)]
        return table.append_column("vector", pa.array(vecs))

    def fake_nn(config, table):
        return _fake_estimator_table_a()

    def fake_rr(config, table):
        return _fake_estimator_table_b()

    def fake_stratify(config, table):
        return {
            "drawer_ids": ["d000", "d001"],
            "strata_sizes": {"wing_a": 6, "wing_b": 4},
            "allocation": {"wing_a": 1, "wing_b": 1},
            "seed": config.seed,
        }

    def fake_c(config, table, subsample):
        # simulate skip (matches "provider unavailable" branch)
        return None

    def fake_analysis(config, ta, tb, tc):
        return {
            "correlations": {"A vs B": {"rho": 0.5, "ci_lo": 0.2, "ci_hi": 0.8, "n": 10}},
            "heterogeneity": {"wing": {"H": 1.5, "p_value": 0.2, "epsilon_squared": 0.05}},
            "decay_fits": {},
        }

    def fake_h3(config, table_b, lme_table):
        mocks.h3_called_with_lme = lme_table
        if not config.run_h3 or lme_table is None:
            return None
        return {"uniform": 0.5, 25: 0.45}

    monkeypatch.setattr(run_experiment, "_stage_snapshot", fake_snapshot)
    monkeypatch.setattr(run_experiment, "_stage_load_palace", fake_load_palace)
    monkeypatch.setattr(run_experiment, "_stage_load_lme", fake_load_lme)
    monkeypatch.setattr(run_experiment, "_stage_normalize", fake_normalize)
    monkeypatch.setattr(run_experiment, "_stage_embed", fake_embed)
    monkeypatch.setattr(run_experiment, "_stage_nn_novelty", fake_nn)
    monkeypatch.setattr(run_experiment, "_stage_recon_residual", fake_rr)
    monkeypatch.setattr(run_experiment, "_stage_stratify", fake_stratify)
    monkeypatch.setattr(run_experiment, "_stage_llm_surprise", fake_c)
    monkeypatch.setattr(run_experiment, "_stage_analysis", fake_analysis)
    monkeypatch.setattr(run_experiment, "_stage_h3", fake_h3)
    return mocks


def test_run_pipeline_skips_lme_when_source_none(tmp_path, monkeypatch):
    mocks = _patch_all_stages(monkeypatch, tmp_path, lme_source=None)

    cfg = run_experiment.Config(
        palace_src=tmp_path / "palace",
        cache_dir=tmp_path / "cache",
        lme_source=None,
        results_yaml_path=tmp_path / "results.yaml",
        run_h3=True,  # H3 flag ON, but lme_source is None -> still skipped
    )
    result = run_experiment.run_pipeline(cfg)

    # H3 stage was called but received lme_table=None; our fake returned None.
    assert mocks.h3_called_with_lme is None
    assert result["h3"] is None

    # results.yaml still gets written
    assert (tmp_path / "results.yaml").exists()


# ---------------------------------------------------------------------------
# 3. results.yaml is written and parses
# ---------------------------------------------------------------------------


def test_run_pipeline_writes_results_yaml(tmp_path, monkeypatch):
    _patch_all_stages(monkeypatch, tmp_path, lme_source=tmp_path / "lme.json")
    # Make sure the H3 branch fires (lme_source is a real Path).
    (tmp_path / "lme.json").write_text("[]")

    cfg = run_experiment.Config(
        palace_src=tmp_path / "palace",
        cache_dir=tmp_path / "cache",
        lme_source=tmp_path / "lme.json",
        results_yaml_path=tmp_path / "results.yaml",
    )
    run_experiment.run_pipeline(cfg)

    out = tmp_path / "results.yaml"
    assert out.exists()
    parsed = yaml.safe_load(out.read_text())
    assert "tables" in parsed
    assert "headline_numbers" in parsed
    # correlations bucket propagated from fake_analysis
    assert "correlations" in parsed["tables"]
    assert "A vs B" in parsed["tables"]["correlations"]
    # headline pulled from fake_h3
    assert parsed["headline_numbers"]["H3_r5_baseline"] == 0.5
    assert parsed["headline_numbers"]["n_drawers_total"] == 10


# ---------------------------------------------------------------------------
# 4. --force nukes caches under cache_dir
# ---------------------------------------------------------------------------


def test_force_clears_known_caches(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "palace_table.parquet").write_bytes(b"old")
    (cache_dir / "estimators_A.parquet").write_bytes(b"old")
    (cache_dir / "estimator_C_partials").mkdir()
    (cache_dir / "unrelated.txt").write_text("keep me")

    run_experiment._clear_caches(cache_dir)

    assert not (cache_dir / "palace_table.parquet").exists()
    assert not (cache_dir / "estimators_A.parquet").exists()
    assert not (cache_dir / "estimator_C_partials").exists()
    # untouched
    assert (cache_dir / "unrelated.txt").exists()


# ---------------------------------------------------------------------------
# 5. CLI entry point smoke — parses args + surfaces missing-palace error
# ---------------------------------------------------------------------------


def test_main_exits_2_when_palace_missing(tmp_path, capsys):
    with patch.object(run_experiment, "run_pipeline", side_effect=FileNotFoundError("nope")):
        rc = run_experiment.main(
            [
                "--palace-src",
                str(tmp_path / "does-not-exist"),
                "--cache-dir",
                str(tmp_path / "cache"),
            ]
        )
    assert rc == 2
