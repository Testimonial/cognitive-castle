"""H3 — LongMemEval R@5 under info-weighted corpus.

Aggregates drawer-level recon_residual to session-level scores (mean),
drops bottom-X% of sessions, then filters each LME entry's
haystack_session_ids/sessions/dates arrays in lockstep before retrieval.

Per Task 0 spike findings: the LME harness rebuilds its retrieval
index per question from these three arrays, so trimming them is the
entire filter mechanism — no harness refactor needed.

Note on LME harness API (verified against benchmarks/longmemeval_bench.py):
- ``build_palace_and_retrieve(entry, granularity="session", n_results=50)``
  returns ``(rankings, corpus, corpus_ids, corpus_timestamps)`` — a 4-tuple.
- ``evaluate_retrieval(rankings, correct_ids, corpus_ids, k)`` returns
  ``(recall_any, recall_all, ndcg_score)`` — a 3-tuple. We use ``recall_any``
  as R@5.
"""

from __future__ import annotations

import statistics

import pyarrow as pa


def aggregate_to_session_scores(
    table: pa.Table,
    info_col: str = "recon_residual",
    session_col: str = "session_id",
) -> dict:
    """Drawer-level info → session-level mean. Sessions with all-null
    drawers are excluded (cannot be info-weighted)."""
    rows = table.to_pylist()
    by_session: dict = {}
    for r in rows:
        sid = r.get(session_col)
        score = r.get(info_col)
        if sid is None or score is None:
            if sid is not None:
                by_session.setdefault(sid, [])
            continue
        by_session.setdefault(sid, []).append(score)
    return {sid: statistics.mean(scores) for sid, scores in by_session.items() if scores}


def drop_bottom_sessions_by_info(session_scores: dict, threshold_pct: float) -> set:
    """Return the set of session_ids to KEEP (i.e., top (100-X)% by score)."""
    items = sorted(session_scores.items(), key=lambda kv: kv[1])
    n = len(items)
    drop_n = int(n * threshold_pct / 100)
    return {sid for sid, _ in items[drop_n:]}


def apply_drop_filter(entry: dict, drop_ids: set) -> dict:
    """Trim haystack_sessions/session_ids/dates in lockstep.
    Returns a new dict; does not mutate input."""
    sessions, sids, dates = [], [], []
    for s, sid, d in zip(
        entry["haystack_sessions"],
        entry["haystack_session_ids"],
        entry["haystack_dates"],
    ):
        if sid in drop_ids:
            continue
        sessions.append(s)
        sids.append(sid)
        dates.append(d)
    out = dict(entry)
    out["haystack_sessions"] = sessions
    out["haystack_session_ids"] = sids
    out["haystack_dates"] = dates
    return out


def _run_lme_with_filter(entries: list, drop_ids: set) -> float:
    """Invoke the LME harness with each entry filtered by drop_ids.
    Returns mean R@5 across entries.

    drop_ids empty → uniform baseline.

    Uses ``build_palace_and_retrieve`` (session granularity) and
    ``evaluate_retrieval`` from ``benchmarks.longmemeval_bench``. Passes
    ``n_results=5`` and reads ``recall_any`` from the 3-tuple as R@5.
    """
    # Imports kept lazy to keep test mocking simple
    from benchmarks.longmemeval_bench import (
        build_palace_and_retrieve,
        evaluate_retrieval,
    )

    recalls = []
    for entry in entries:
        filtered = apply_drop_filter(entry, drop_ids)
        if not filtered["haystack_session_ids"]:
            continue  # nothing left to retrieve against
        rankings, _corpus, corpus_ids, _corpus_ts = build_palace_and_retrieve(filtered, n_results=5)
        correct_ids = filtered.get("answer_session_ids", [])
        recall_any, _recall_all, _ndcg = evaluate_retrieval(rankings, correct_ids, corpus_ids, k=5)
        recalls.append(recall_any)
    return sum(recalls) / len(recalls) if recalls else 0.0


def run_h3_experiment(
    drawer_table: pa.Table,
    lme_entries: list,
    thresholds: tuple = (10, 25, 50),
) -> dict:
    """Returns {"uniform": R@5, 10: R@5, 25: R@5, 50: R@5}."""
    session_scores = aggregate_to_session_scores(drawer_table)
    results = {"uniform": _run_lme_with_filter(lme_entries, drop_ids=set())}
    all_sessions = set(session_scores.keys())
    for t in thresholds:
        keep = drop_bottom_sessions_by_info(session_scores, threshold_pct=t)
        drop = all_sessions - keep
        results[t] = _run_lme_with_filter(lme_entries, drop_ids=drop)
    return results
