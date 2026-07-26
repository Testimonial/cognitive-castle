"""Unit test for the bench's info-weight demotion hook (2026-07-26 spec).

The full R@5 A/B run is a manual gate documented in the spec; this file
only pins the demotion arithmetic the bench applies when --info-weight
is passed.

Import note: ``benchmarks.longmemeval_bench`` cannot be imported by dotted
path under pytest here — ``tests/benchmarks/__init__.py`` (an unrelated,
pre-existing performance-benchmark test package) shadows the top-level
``benchmarks`` package name once pytest prepends ``tests/`` onto
``sys.path`` for this module's collection (pytest's default "prepend"
import mode inserts the first ``__init__.py``-less ancestor directory of
the test file — here ``tests/`` itself — ahead of the repo root, and a
regular package with an ``__init__.py`` wins over a namespace package with
no merging). This reproduces even with ``--ignore=tests/benchmarks``,
since the shadowing package is discovered via ``sys.path``, not via
collection. Loading the module directly from its file path sidesteps
package resolution entirely and needs no changes to production code or
package layout.
"""

import importlib.util
from pathlib import Path

_BENCH_PATH = Path(__file__).resolve().parent.parent / "benchmarks" / "longmemeval_bench.py"
_spec = importlib.util.spec_from_file_location("longmemeval_bench", _BENCH_PATH)
_longmemeval_bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_longmemeval_bench)

apply_bench_info_weight = _longmemeval_bench.apply_bench_info_weight


def test_bench_demotes_low_novelty_session():
    # (session_id, score, novelty)
    ranked = [("dup", 0.9, 0.02), ("fresh", 0.8, 0.9)]
    out = apply_bench_info_weight(ranked, threshold=0.10, min_factor=0.5)
    # dup: 0.9 * (0.5 + 0.5*0.2) = 0.54 ; fresh: 0.8 → fresh first
    assert [sid for sid, _, _ in out] == ["fresh", "dup"]


def test_bench_none_novelty_untouched():
    ranked = [("a", 0.9, None)]
    out = apply_bench_info_weight(ranked, threshold=0.10, min_factor=0.5)
    assert out[0][1] == 0.9
