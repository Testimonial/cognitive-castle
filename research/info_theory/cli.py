"""Single-CLI orchestration for the info_theory research pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

CACHE_DIR_DEFAULT = Path.home() / ".castle" / "research"

# Stage registry: name -> entry-point function
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
    fig_p.add_argument(
        "--tables",
        action="store_true",
        help="emit appendix LaTeX tables from results.yaml",
    )
    ce = sub.add_parser("cost-estimate", help="dry-run cost estimator")
    ce.add_argument("--stage")
    return p


def _run_stage(name: str, force: bool):
    if name not in STAGES:
        raise KeyError(f"unknown stage {name}")
    import importlib

    mod_path, fn = STAGES[name].split(":")
    mod = importlib.import_module(mod_path)
    getattr(mod, fn)(force=force)


def cmd_snapshot():
    import yaml

    from pipeline.snapshot_palace import compute_fingerprint, snapshot_palace

    src = Path.home() / ".castle" / "palace"
    dst = CACHE_DIR_DEFAULT / "palace_snapshot_2026-05-16"
    snapshot_palace(src, dst)
    # Compute and record fingerprint
    from pipeline.load_palace import load_palace

    table = load_palace(dst)
    rows = [
        {"drawer_id": d, "filed_at": f, "chunk_index": c}
        for d, f, c in zip(
            table.column("drawer_id").to_pylist(),
            table.column("filed_at").to_pylist(),
            table.column("chunk_index").to_pylist(),
        )
    ]
    fp = compute_fingerprint(rows)
    seeds_path = Path(__file__).parent / "seeds.yaml"
    with open(seeds_path) as f:
        seeds = yaml.safe_load(f)
    seeds["palace_snapshot_fingerprint"] = fp
    with open(seeds_path, "w") as f:
        yaml.dump(seeds, f)
    print(f"Snapshot written. Fingerprint: {fp}")


def cmd_pilot():
    print("[pilot] Running 5% LME sample to tighten corpus-size estimate...")
    # Implementation: load 5% of LME, run through miner, count drawers
    import json
    import tempfile

    from benchmarks.longmemeval_bench import load_questions
    from pipeline.load_longmemeval import load_longmemeval

    all_qs = load_questions()
    sample = all_qs[: len(all_qs) // 20]
    # Save sample to tmp + run load
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(sample, f)
        tmp = f.name
    table = load_longmemeval(tmp)
    est = table.num_rows * 20
    print(f"[pilot] 5% sample -> {table.num_rows} drawers. Estimated total: ~{est}")


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
    print(
        f"Estimated cost for stage '{stage}': ${result['mean']:.2f} "
        f"(range ${result['lo']:.2f}-${result['hi']:.2f})"
    )


def dispatch(args):
    if args.command == "snapshot":
        cmd_snapshot()
    elif args.command == "pilot":
        cmd_pilot()
    elif args.command == "status":
        cmd_status()
    elif args.command == "figures":
        cmd_figures(tables=args.tables)
    elif args.command == "cost-estimate":
        cmd_cost_estimate(args.stage)
    elif args.command == "run":
        if args.all:
            for s in STAGES.keys():
                _run_stage(s, args.force)
        elif args.stage:
            _run_stage(args.stage, args.force)
        else:
            print("Specify --stage X or --all")
            sys.exit(2)


def main():
    args = build_arg_parser().parse_args()
    dispatch(args)


if __name__ == "__main__":
    main()
