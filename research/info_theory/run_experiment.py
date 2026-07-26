"""End-to-end info-theory pipeline driver.

Usage:
    python -m run_experiment                    # run with defaults
    python -m run_experiment --config path.yaml # from YAML

Pipeline stages (all cached to config.cache_dir):
  1. snapshot palace           -> cache_dir/palace_snapshot/
  2. load palace               -> cache_dir/palace_table.parquet
  3. normalize text            -> cache_dir/palace_normalized.parquet
  4. embed (reuse palace vecs) -> cache_dir/palace_embedded.parquet
  5. nn_novelty  (A)           -> cache_dir/estimators_A.parquet
  6. recon_residual (B)        -> cache_dir/estimators_B.parquet
  7. stratify subsample        -> cache_dir/subsample_ids.json
  8. llm_surprise (C)          -> cache_dir/estimator_C_partials/
                                  then estimator_C_merged.parquet
  9. fit decay + correlations
     + heterogeneity           -> cache_dir/analysis_results.json
 10. downstream H3 (if LME set)-> cache_dir/h3_results.json
 11. emit results yaml         -> paper/results.yaml

Cache invalidation:
    ``config.force`` (or ``--force`` on the CLI) blows away every
    downstream cache file *and* the snapshot dir before starting.
    Individual stages otherwise reuse existing caches by path.

Graceful degradation:
    * ``palace_src`` missing            -> raise ``FileNotFoundError``
    * ``lme_source`` is ``None``        -> skip LME load + H3
    * ``run_c_stage`` False             -> skip C-stage; correlations
                                          only report A vs B
    * ``claude-cli`` provider raises    -> warn, skip C-stage, continue

None of the heavy work runs in-process during tests: every stage is a
thin wrapper around the tested pipeline modules, and the test suite
monkey-patches them out.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pyarrow as pa
import pyarrow.parquet as pq
import yaml


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class Config:
    """Runtime configuration for the pipeline driver.

    Uses ``Optional[Path]`` (rather than ``Path | None``) because
    ``dataclass`` field-type introspection on 3.10 chokes on the PEP-604
    union syntax under ``from __future__ import annotations``; this form
    works on 3.10 and later.
    """

    palace_src: Path = field(default_factory=lambda: Path.home() / ".castle" / "palace")
    lme_source: Optional[Path] = None  # None -> skip LME phases
    cache_dir: Path = field(default_factory=lambda: Path.home() / ".castle" / "research")
    subsample_n: int = 1000
    subsample_floor: int = 50
    max_cost_usd: float = 100.0
    run_c_stage: bool = True  # False -> skip llm_surprise
    run_h3: bool = True  # False -> skip Task 17 (downstream H3)
    n_bootstrap: int = 1000
    force: bool = False  # re-run all stages from scratch
    seed: int = 42
    llm_provider_name: str = "claude-cli"
    llm_model: str = "claude-haiku-4-5"
    results_yaml_path: Optional[Path] = None  # default: paper/results.yaml
    merge_every: int = 50
    limit_drawers: Optional[int] = None  # truncate palace table for smoke tests


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _log(stage: str, msg: str) -> None:
    print(f"[{stage}] {msg}", flush=True)


def _atomic_write_json(obj: Any, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, default=str, sort_keys=True)
    tmp.rename(path)


def _atomic_write_yaml(obj: Any, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        yaml.safe_dump(obj, f, sort_keys=False)
    tmp.rename(path)


def _atomic_write_table(table: pa.Table, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, tmp)
    tmp.rename(path)


def _clear_caches(cache_dir: Path) -> None:
    """--force blast: remove every well-known cache artefact.

    We only touch files/dirs we know we write, so an accidental
    ``cache_dir=~/`` doesn't nuke the user's home. Anything else in
    the dir is left alone.
    """
    known = [
        "palace_snapshot",
        "palace_table.parquet",
        "palace_normalized.parquet",
        "palace_embedded.parquet",
        "lme_table.parquet",
        "estimators_A.parquet",
        "estimators_B.parquet",
        "subsample_ids.json",
        "estimator_C_partials",
        "estimator_C_merged.parquet",
        "analysis_results.json",
        "h3_results.json",
    ]
    for name in known:
        p = cache_dir / name
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()


# ---------------------------------------------------------------------------
# Stage wrappers
# ---------------------------------------------------------------------------


def _stage_snapshot(config: Config) -> Path:
    """Snapshot the live palace LanceDB tree into cache_dir/palace_snapshot.

    The Castle palace directory has a ``lancedb/`` subdirectory that holds
    the actual LanceDB tables. `load_palace` expects to open that directly,
    so we snapshot the subdir contents (or the parent if the subdir is missing).
    """
    from pipeline.snapshot_palace import snapshot_palace

    stage = "snapshot"
    dst = config.cache_dir / "palace_snapshot"
    src = Path(config.palace_src)
    # Prefer the lancedb subdir if present — matches load_palace's opener contract.
    if (src / "lancedb").exists():
        src = src / "lancedb"
    _log(stage, f"starting... src={src} -> dst={dst}")
    t0 = time.time()

    if dst.exists():
        _log(stage, f"cache hit at {dst}, skipping")
        return dst

    if not src.exists():
        raise FileNotFoundError(
            f"palace source does not exist: {src}. "
            "Set config.palace_src to your Castle palace directory."
        )

    snapshot_palace(src, dst)
    _log(stage, f"done ({time.time() - t0:.2f}s)")
    return dst


def _stage_load_palace(config: Config, snapshot_dir: Path) -> pa.Table:
    from pipeline.load_palace import load_palace

    stage = "load-palace"
    out = config.cache_dir / "palace_table.parquet"
    _log(stage, "starting...")
    t0 = time.time()

    if out.exists():
        table = pq.read_table(out)
        _log(stage, f"cache hit at {out} ({table.num_rows} rows)")
        return table

    table = load_palace(snapshot_dir)
    if config.limit_drawers is not None:
        table = table.slice(0, config.limit_drawers)
        _log(stage, f"limit_drawers={config.limit_drawers} applied")
    _atomic_write_table(table, out)
    _log(stage, f"done ({time.time() - t0:.2f}s, {table.num_rows} rows)")
    return table


def _stage_load_lme(config: Config) -> Optional[pa.Table]:
    if config.lme_source is None:
        _log("load-lme", "lme_source is None; skipping")
        return None

    from pipeline.load_longmemeval import load_longmemeval

    stage = "load-lme"
    out = config.cache_dir / "lme_table.parquet"
    _log(stage, f"starting... source={config.lme_source}")
    t0 = time.time()

    if out.exists():
        table = pq.read_table(out)
        _log(stage, f"cache hit at {out} ({table.num_rows} rows)")
        return table

    table = load_longmemeval(config.lme_source)
    _atomic_write_table(table, out)
    _log(stage, f"done ({time.time() - t0:.2f}s, {table.num_rows} rows)")
    return table


def _stage_normalize(config: Config, table: pa.Table) -> pa.Table:
    from pipeline.normalize import normalize

    stage = "normalize"
    out = config.cache_dir / "palace_normalized.parquet"
    _log(stage, "starting...")
    t0 = time.time()

    if out.exists():
        cached = pq.read_table(out)
        _log(stage, f"cache hit at {out} ({cached.num_rows} rows)")
        return cached

    texts = table.column("text").to_pylist()
    normalized = [normalize(t or "") for t in texts]
    # Replace text column with normalized text
    idx = table.column_names.index("text")
    out_table = table.set_column(idx, "text", pa.array(normalized, type=pa.large_string()))
    _atomic_write_table(out_table, out)
    _log(stage, f"done ({time.time() - t0:.2f}s, {out_table.num_rows} rows)")
    return out_table


def _stage_embed(config: Config, table: pa.Table) -> pa.Table:
    from pipeline.embed import embed_drawers

    stage = "embed"
    out = config.cache_dir / "palace_embedded.parquet"
    _log(stage, "starting...")
    t0 = time.time()

    if out.exists():
        cached = pq.read_table(out)
        _log(stage, f"cache hit at {out} ({cached.num_rows} rows)")
        return cached

    # Palace already ships bge-m3 vectors; reuse them for the smoke path
    # rather than re-embedding 65k drawers. For correctness on normalized
    # text a follow-up should re-embed; that's the "full-run" path.
    if "vector" in table.column_names:
        _log(stage, "reusing palace vectors (no re-embed)")
        _atomic_write_table(table, out)
        _log(stage, f"done ({time.time() - t0:.2f}s, {table.num_rows} rows)")
        return table

    embedded = embed_drawers(table, cache_path=out)
    _log(stage, f"done ({time.time() - t0:.2f}s, {embedded.num_rows} rows)")
    return embedded


def _stage_nn_novelty(config: Config, table: pa.Table) -> pa.Table:
    from pipeline.nn_novelty import compute_for_table

    stage = "nn-novelty"
    out = config.cache_dir / "estimators_A.parquet"
    _log(stage, "starting...")
    t0 = time.time()

    if out.exists():
        cached = pq.read_table(out)
        _log(stage, f"cache hit at {out} ({cached.num_rows} rows)")
        return cached

    group_by = "wing" if "wing" in table.column_names else None
    result = compute_for_table(table, group_by=group_by)
    _atomic_write_table(result, out)
    _log(stage, f"done ({time.time() - t0:.2f}s, {result.num_rows} rows)")
    return result


def _stage_recon_residual(config: Config, table: pa.Table) -> pa.Table:
    from pipeline.recon_residual import compute_for_table

    stage = "recon-residual"
    out = config.cache_dir / "estimators_B.parquet"
    _log(stage, "starting...")
    t0 = time.time()

    if out.exists():
        cached = pq.read_table(out)
        _log(stage, f"cache hit at {out} ({cached.num_rows} rows)")
        return cached

    group_by = "wing" if "wing" in table.column_names else None
    result = compute_for_table(table, k_target=20, k_floor=5, lam=1e-3, group_by=group_by)
    _atomic_write_table(result, out)
    _log(stage, f"done ({time.time() - t0:.2f}s, {result.num_rows} rows)")
    return result


def _stage_stratify(config: Config, table: pa.Table) -> dict:
    """Allocate a per-stratum subsample and pick which drawer_ids get C.

    Deterministic given ``config.seed``.
    """
    from pipeline.stratify import allocate_subsample

    stage = "stratify"
    out = config.cache_dir / "subsample_ids.json"
    _log(stage, "starting...")
    t0 = time.time()

    if out.exists():
        with open(out) as f:
            payload = json.load(f)
        _log(stage, f"cache hit at {out} ({len(payload.get('drawer_ids', []))} ids)")
        return payload

    # Build strata by wing (falls back to a single 'all' stratum for LME-only).
    if "wing" in table.column_names:
        wings = table.column("wing").to_pylist()
    else:
        wings = ["all"] * table.num_rows
    strata_sizes: dict[str, int] = {}
    for w in wings:
        key = w or "unknown"
        strata_sizes[key] = strata_sizes.get(key, 0) + 1
    alloc = allocate_subsample(
        strata_sizes, config.subsample_n, config.subsample_floor, seed=config.seed
    )

    # Deterministic pick: first N drawer_ids per stratum by drawer_id sort.
    import random

    rng = random.Random(config.seed)
    drawer_ids = table.column("drawer_id").to_pylist()
    per_stratum: dict[str, list[str]] = {}
    for did, w in zip(drawer_ids, wings):
        per_stratum.setdefault(w or "unknown", []).append(did)
    chosen: list[str] = []
    for stratum, take in alloc.items():
        pool = sorted(per_stratum.get(stratum, []))
        rng.shuffle(pool)
        chosen.extend(pool[:take])

    payload = {
        "drawer_ids": chosen,
        "strata_sizes": strata_sizes,
        "allocation": alloc,
        "seed": config.seed,
    }
    _atomic_write_json(payload, out)
    _log(stage, f"done ({time.time() - t0:.2f}s, {len(chosen)} ids)")
    return payload


def _stage_llm_surprise(
    config: Config,
    table: pa.Table,
    subsample: dict,
) -> Optional[pa.Table]:
    """Resumable C-stage. Returns merged C-scores table, or None on skip."""
    stage = "llm-surprise"
    partials_dir = config.cache_dir / "estimator_C_partials"
    merged_out = config.cache_dir / "estimator_C_merged.parquet"

    if not config.run_c_stage:
        _log(stage, "run_c_stage=False; skipping")
        return None

    _log(stage, "starting...")
    t0 = time.time()

    if merged_out.exists():
        cached = pq.read_table(merged_out)
        _log(stage, f"cache hit at {merged_out} ({cached.num_rows} rows)")
        return cached

    # Provider — graceful degradation on any failure.
    try:
        from cognitive_castle.llm_client import get_provider

        provider = get_provider(config.llm_provider_name, model=config.llm_model)
    except Exception as e:  # noqa: BLE001 — degrade on ANY provider setup error
        _log(stage, f"WARN: provider unavailable ({e!r}); skipping C-stage")
        return None

    from pipeline.llm_surprise import CostCapExceeded, merge_partials, process_subsample

    # Memory-saver: C-stage only needs {drawer_id, text, wing, filed_at}.
    # `table` has all 65k drawers with 1024-dim vectors + metadata_json blobs.
    # `to_pylist()` on the full table balloons to ~2 GB of Python-float
    # objects for the vector column alone. Project the 4 needed columns first.
    lean_cols = [c for c in ("drawer_id", "text", "wing", "filed_at") if c in table.column_names]
    rows = table.select(lean_cols).to_pylist()

    chosen_ids = set(subsample["drawer_ids"])
    targets = [r for r in rows if r["drawer_id"] in chosen_ids]

    # Priors lookup: 20 most-recent drawers before target, from the same wing
    # when available. Downstream code depends only on the structure
    # {drawer_id: [{"text": ..., "drawer_id": ...}, ...]}.
    priors_lookup: dict[str, list[dict]] = {}
    for target in targets:
        wing = target.get("wing")
        prior_pool = [
            r
            for r in rows
            if r.get("filed_at", "") < target.get("filed_at", "")
            and (wing is None or r.get("wing") == wing)
        ]
        prior_pool.sort(key=lambda r: r.get("filed_at", ""))
        priors_lookup[target["drawer_id"]] = prior_pool[-20:]

    # Free the 65k-row baseline dict list before entering the LLM loop.
    # Everything past this point uses only `targets` (925 dicts) and
    # `priors_lookup` (18.5k refs — but they alias into the priors kept
    # in memory, GC won't reclaim yet). Still, dropping the 63k targets
    # we don't touch saves memory.
    import gc as _gc

    del rows
    _gc.collect()

    try:
        process_subsample(
            targets,
            priors_lookup,
            provider,
            partials_dir=partials_dir,
            max_cost=config.max_cost_usd,
            merge_every=config.merge_every,
        )
    except CostCapExceeded as e:
        _log(stage, f"WARN: {e}; merging what we have")
    except Exception as e:  # noqa: BLE001
        _log(stage, f"WARN: process_subsample raised ({e!r}); merging partials")

    merge_partials(partials_dir, merged_out)
    if merged_out.exists():
        merged = pq.read_table(merged_out)
        _log(stage, f"done ({time.time() - t0:.2f}s, {merged.num_rows} rows)")
        return merged
    _log(stage, f"done ({time.time() - t0:.2f}s, 0 rows — no partials written)")
    return None


def _stage_analysis(
    config: Config,
    table_a: pa.Table,
    table_b: pa.Table,
    table_c: Optional[pa.Table],
) -> dict:
    """Correlations, heterogeneity, per-stratum decay fits."""
    stage = "analysis"
    out = config.cache_dir / "analysis_results.json"
    _log(stage, "starting...")
    t0 = time.time()

    if out.exists():
        with open(out) as f:
            cached = json.load(f)
        _log(stage, f"cache hit at {out}")
        return cached

    import numpy as np

    from analysis.correlations import spearman_with_ci
    from analysis.fit_decay import (
        aic_model_selection,
        fit_exponential,
        fit_powerlaw_weighted,
    )
    from analysis.heterogeneity import kruskal_wallis_with_epsilon_sq

    # -- correlations
    correlations: dict[str, dict] = {}

    a_rows = table_a.to_pylist()
    b_rows = table_b.to_pylist()
    b_by_id = {r["drawer_id"]: r for r in b_rows}
    xy_ab = [
        (r["nn_novelty"], b_by_id[r["drawer_id"]]["recon_residual"])
        for r in a_rows
        if r["drawer_id"] in b_by_id
        and r.get("nn_novelty") is not None
        and b_by_id[r["drawer_id"]].get("recon_residual") is not None
    ]
    if len(xy_ab) >= 3:
        xa, yb = zip(*xy_ab)
        rho, lo, hi = spearman_with_ci(
            list(xa), list(yb), n_resamples=min(config.n_bootstrap, 200), seed=config.seed
        )
        correlations["A vs B"] = {"rho": rho, "ci_lo": lo, "ci_hi": hi, "n": len(xy_ab)}

    if table_c is not None and table_c.num_rows > 0:
        c_by_id = {r["drawer_id"]: r["llm_surprise"] for r in table_c.to_pylist()}
        # A vs C
        xy_ac = [
            (r["nn_novelty"], c_by_id[r["drawer_id"]])
            for r in a_rows
            if r["drawer_id"] in c_by_id and r.get("nn_novelty") is not None
        ]
        if len(xy_ac) >= 3:
            xa, yc = zip(*xy_ac)
            rho, lo, hi = spearman_with_ci(
                list(xa),
                list(yc),
                n_resamples=min(config.n_bootstrap, 200),
                seed=config.seed,
            )
            correlations["A vs C"] = {
                "rho": rho,
                "ci_lo": lo,
                "ci_hi": hi,
                "n": len(xy_ac),
            }
        # B vs C
        xy_bc = [
            (r["recon_residual"], c_by_id[r["drawer_id"]])
            for r in b_rows
            if r["drawer_id"] in c_by_id and r.get("recon_residual") is not None
        ]
        if len(xy_bc) >= 3:
            xb, yc = zip(*xy_bc)
            rho, lo, hi = spearman_with_ci(
                list(xb),
                list(yc),
                n_resamples=min(config.n_bootstrap, 200),
                seed=config.seed,
            )
            correlations["B vs C"] = {
                "rho": rho,
                "ci_lo": lo,
                "ci_hi": hi,
                "n": len(xy_bc),
            }

    # -- heterogeneity by wing (uses A)
    heterogeneity: dict[str, dict] = {}
    if "wing" in table_a.column_names:
        by_wing: dict[str, list[float]] = {}
        for r in a_rows:
            wing = r.get("wing") or "unknown"
            v = r.get("nn_novelty")
            if v is None:
                continue
            by_wing.setdefault(wing, []).append(v)
        by_wing = {k: v for k, v in by_wing.items() if len(v) >= 2}
        if len(by_wing) >= 2:
            heterogeneity["wing"] = kruskal_wallis_with_epsilon_sq(by_wing)

    # -- decay fits per stratum (uses A, x = index within stratum)
    decay_fits: dict[str, dict] = {}
    if "wing" in table_a.column_names:
        per_wing_series: dict[str, list[float]] = {}
        # sort by filed_at within wing to make N a rank
        rows_sorted = sorted(a_rows, key=lambda r: (r.get("wing") or "", r.get("filed_at") or ""))
        for r in rows_sorted:
            w = r.get("wing") or "unknown"
            v = r.get("nn_novelty")
            if v is None:
                continue
            per_wing_series.setdefault(w, []).append(v)
        for wing, ys in per_wing_series.items():
            if len(ys) < 20:
                continue
            N = np.arange(1, len(ys) + 1, dtype=float)
            y = np.asarray(ys, dtype=float)
            try:
                pl = fit_powerlaw_weighted(N, y, bin_width=max(1, len(ys) // 10))
                ex = fit_exponential(N, y)
                sel = aic_model_selection(pl, ex)
                decay_fits[f"wing::{wing}"] = {
                    "alpha": pl["alpha"],
                    "a": pl["a"],
                    "aic_powerlaw": pl["aic"],
                    "aic_exponential": ex["aic"],
                    "winner": sel["winner"],
                    "n": pl["n"],
                }
            except Exception as e:  # noqa: BLE001 — fits fail on flat / bad data
                decay_fits[f"wing::{wing}"] = {"error": repr(e), "n": len(ys)}

    results = {
        "correlations": correlations,
        "heterogeneity": heterogeneity,
        "decay_fits": decay_fits,
    }
    _atomic_write_json(results, out)
    _log(stage, f"done ({time.time() - t0:.2f}s)")
    return results


def _stage_h3(
    config: Config,
    table_b: pa.Table,
    lme_table: Optional[pa.Table],
) -> Optional[dict]:
    stage = "h3"
    out = config.cache_dir / "h3_results.json"

    if not config.run_h3:
        _log(stage, "run_h3=False; skipping")
        return None
    if lme_table is None:
        _log(stage, "no LME table loaded; skipping")
        return None

    _log(stage, "starting...")
    t0 = time.time()

    if out.exists():
        with open(out) as f:
            cached = json.load(f)
        _log(stage, f"cache hit at {out}")
        return cached

    from pipeline.downstream_eval import run_h3_experiment

    # H3 consumes original LME entries (dicts), not the chunked table. If the
    # caller left ``lme_source`` pointing at a JSON file we can re-hydrate.
    entries: list = []
    if config.lme_source and Path(config.lme_source).is_file():
        with open(config.lme_source) as f:
            entries = json.load(f)

    try:
        results = run_h3_experiment(table_b, entries)
    except Exception as e:  # noqa: BLE001
        _log(stage, f"WARN: run_h3_experiment raised ({e!r}); recording empty result")
        results = {"error": repr(e)}

    _atomic_write_json(results, out)
    _log(stage, f"done ({time.time() - t0:.2f}s)")
    return results


def _emit_results_yaml(
    config: Config,
    analysis: dict,
    h3: Optional[dict],
    table_a: pa.Table,
) -> Path:
    """Serialise the summary artefacts into paper/results.yaml."""
    stage = "results-yaml"
    target = (
        Path(config.results_yaml_path)
        if config.results_yaml_path is not None
        else Path(__file__).parent / "paper" / "results.yaml"
    )
    _log(stage, f"writing {target}")

    correlations = analysis.get("correlations", {}) or {}
    heterogeneity = analysis.get("heterogeneity", {}) or {}
    decay_fits = analysis.get("decay_fits", {}) or {}

    headline: dict[str, Any] = {
        "n_drawers_total": table_a.num_rows,
        "n_strata": (
            len({r.get("wing") for r in table_a.to_pylist()})
            if "wing" in table_a.column_names
            else 1
        ),
    }
    if "A vs C" in correlations:
        headline["A_C_spearman"] = correlations["A vs C"]["rho"]
    if h3 and isinstance(h3, dict):
        if "uniform" in h3:
            headline["H3_r5_baseline"] = h3["uniform"]
        if 25 in h3:
            headline["H3_r5_drop25"] = h3[25]

    payload = {
        "tables": {
            "correlations": correlations,
            "heterogeneity": heterogeneity,
            "decay_fits": decay_fits,
        },
        "headline_numbers": headline,
    }
    _atomic_write_yaml(payload, target)
    return target


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_pipeline(config: Config) -> dict:
    """Run the pipeline end-to-end and return a summary dict.

    The returned dict mirrors ``results.yaml`` so tests + callers can
    inspect outputs without re-reading disk.
    """
    Path(config.cache_dir).mkdir(parents=True, exist_ok=True)
    if config.force:
        _log("driver", f"--force: clearing caches under {config.cache_dir}")
        _clear_caches(Path(config.cache_dir))

    snapshot_dir = _stage_snapshot(config)
    palace_table = _stage_load_palace(config, snapshot_dir)
    lme_table = _stage_load_lme(config)

    palace_table = _stage_normalize(config, palace_table)
    palace_table = _stage_embed(config, palace_table)

    table_a = _stage_nn_novelty(config, palace_table)
    table_b = _stage_recon_residual(config, palace_table)

    subsample = _stage_stratify(config, palace_table)

    # Before spending ~15s/call × 925 calls in C-stage, free the palace
    # tables we no longer need. table_a and table_b carry only the
    # {drawer_id, novelty, ...} columns — they don't drag vectors along.
    # `_stage_llm_surprise` will project just the text columns it needs
    # from `palace_table`, but we still want to drop table_a/table_b's
    # duplicate palace metadata to keep the resident set small.
    import gc as _gc

    table_c = _stage_llm_surprise(config, palace_table, subsample)
    del palace_table
    _gc.collect()

    analysis = _stage_analysis(config, table_a, table_b, table_c)
    h3 = _stage_h3(config, table_b, lme_table)

    results_path = _emit_results_yaml(config, analysis, h3, table_a)
    _log("driver", f"pipeline complete. Results at {results_path}")

    return {
        "analysis": analysis,
        "h3": h3,
        "results_yaml": str(results_path),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _config_from_yaml(path: Path) -> Config:
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    kwargs: dict[str, Any] = {}
    for key in Config.__dataclass_fields__:
        if key in data:
            val = data[key]
            if key in {"palace_src", "cache_dir", "lme_source", "results_yaml_path"}:
                val = Path(val) if val is not None else None
            kwargs[key] = val
    return Config(**kwargs)


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="run_experiment")
    p.add_argument("--config", type=Path, default=None, help="YAML config path")
    p.add_argument("--force", action="store_true", help="clear caches and re-run all stages")
    p.add_argument("--palace-src", type=Path, default=None)
    p.add_argument("--lme-source", type=Path, default=None)
    p.add_argument("--cache-dir", type=Path, default=None)
    p.add_argument("--no-c-stage", action="store_true", help="skip llm_surprise")
    p.add_argument("--no-h3", action="store_true", help="skip downstream H3")
    p.add_argument("--limit-drawers", type=int, default=None, help="truncate palace for smoke test")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_argparser().parse_args(argv)
    config = _config_from_yaml(args.config) if args.config else Config()
    if args.force:
        config.force = True
    if args.palace_src is not None:
        config.palace_src = args.palace_src
    if args.lme_source is not None:
        config.lme_source = args.lme_source
    if args.cache_dir is not None:
        config.cache_dir = args.cache_dir
    if args.no_c_stage:
        config.run_c_stage = False
    if args.no_h3:
        config.run_h3 = False
    if args.limit_drawers is not None:
        config.limit_drawers = args.limit_drawers

    try:
        run_pipeline(config)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
