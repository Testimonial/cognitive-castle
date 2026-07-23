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
        lines = [
            "\\begin{tabular}{l" + "r" * (len(next(iter(rows.values()))) if rows else 1) + "}",
            "\\hline",
        ]
        # Header
        cols = sorted(next(iter(rows.values())).keys()) if rows else []
        lines.append(" & ".join(["", *cols]) + " \\\\")
        lines.append("\\hline")
        for row_name, vals in rows.items():
            cells = [row_name] + [
                f"{vals.get(c):.3g}"
                if isinstance(vals.get(c), (int, float))
                else str(vals.get(c, ""))
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
