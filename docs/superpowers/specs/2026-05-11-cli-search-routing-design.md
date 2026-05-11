# CLI `castle search` Routes Through the New 3-Stage Pipeline

**Date:** 2026-05-11
**Branch target:** develop
**Scope:** Make `castle search` (the shell CLI) use the same 3-stage retrieval pipeline that `search_memories` (the MCP path) uses. Small follow-up to the SOTA retrieval upgrade.

## Background

The SOTA retrieval upgrade (PR #2, commit `facf70da`) shipped a 3-stage retrieval pipeline — parallel recall (dense + FTS + KG-hop) → weighted RRF + recency → cross-encoder rerank — exposed via `search_memories()`. PR #4 deleted the legacy BM25 path from `searcher.py`.

The CLI `castle search` command, implemented as `search(query, palace_path, wing, room, n_results)` in `cognitive_castle/searcher.py:184`, was NOT routed through the new pipeline. It currently calls `col.query(...)` directly — dense vector search only, no FTS, no KG-hop, no reranker.

Result: agents calling `mcp__castle__search` get high-quality reranked results; users running `castle search "..."` from the shell get vector-only results. Same palace, two retrieval qualities.

This was flagged in the PR #2 code review as a known follow-up. This spec fixes it.

## Goals

1. `castle search "query" --palace <path> [--wing X] [--room Y]` returns the same quality results as `search_memories(query, ...)` from MCP.
2. The CLI's printed output shape (header, per-result block, no-results message) is preserved — existing tests that scrape stdout keep passing.
3. The function signature `search(query, palace_path, wing, room, n_results)` is unchanged. Other internal callers (if any) are unaffected.

## Non-goals

- Changes to `search_memories()` or `_new_pipeline_search()` themselves.
- A new CLI flag for "old pipeline" fallback. The new pipeline is the only path.
- Performance tuning of the pipeline (already handled in PR #2).

## Source of truth

Verified by reading the files:

- `cognitive_castle/searcher.py:184-258` — current `search()` implementation. Calls `col.query(...)` on the LanceDB collection directly. Prints `Match: cosine=X` per result.
- `cognitive_castle/searcher.py:261` — `search_memories()` entry point. Routes to `_new_pipeline_search` unconditionally (post-PR #4).
- `cognitive_castle/searcher.py:365` — `_new_pipeline_search(query, palace_path, wing, room, n_results, cfg, is_hook_call)` implementation. Returns `list[dict]` with keys including `id`, `text` (or `document`), `score`, plus metadata fields (`wing`, `room`, `source_file`).
- `_first_or_empty` and `_warn_if_legacy_metric` are referenced from the current `search()` body; check if they remain in use by other callers after this refactor.

## Naming decisions

- **Score label in CLI output:** `score=X` (not `cosine=X`). The displayed value comes from the cross-encoder reranker, not cosine distance. Calling it cosine would mislead. `score` is generic and accurate.
- **Function name:** `search` stays. No new name.
- **`is_hook_call` parameter:** `False` when called from the CLI. Interactive K cap (`cfg.reranker_k_interactive = 20`) applies.

## File-by-file change list

### `cognitive_castle/searcher.py:184-258`

Replace the body of `search()`. New body:

```python
def search(query: str, palace_path: str, wing: str = None, room: str = None, n_results: int = 5):
    """CLI entry point.

    Routes through the 3-stage pipeline (dense + FTS + KG-hop → fuse → rerank),
    same as `search_memories()`. Prints results to stdout in the legacy format
    so existing scraping tests keep working. Score shown is the cross-encoder
    reranker score, not cosine distance.

    Raises SearchError if the pipeline fails. Returns None either way (this is
    a print-only function — programmatic callers should use `search_memories`).
    """
    from .config import CognitiveCastleConfig
    cfg = CognitiveCastleConfig()

    try:
        hits = _new_pipeline_search(
            query, palace_path, wing, room, n_results, cfg, is_hook_call=False
        )
    except Exception as e:
        print(f"\n  Search error: {e}")
        raise SearchError(f"Search error: {e}") from e

    if not hits:
        print(f'\n  No results found for: "{query}"')
        return

    print(f"\n{'=' * 60}")
    print(f'  Results for: "{query}"')
    if wing:
        print(f"  Wing: {wing}")
    if room:
        print(f"  Room: {room}")
    print(f"{'=' * 60}\n")

    for i, hit in enumerate(hits, 1):
        text = hit.get("text") or hit.get("document", "")
        score = round(float(hit.get("score", 0.0)), 3)
        wing_name = hit.get("wing", "?")
        room_name = hit.get("room", "?")
        source = Path(hit.get("source_file", "?")).name

        print(f"  [{i}] {wing_name} / {room_name}")
        print(f"      Source: {source}")
        print(f"      Match:  score={score}\n")
        print(f"      {text}\n")
        print(f"  {'─' * 56}")
```

The function's signature and the printed structure (header, "No results", per-result block with `[N] wing / room / Source / Match / text / separator`) match the prior layout, except `cosine=` becomes `score=`. The separator (`─` repeated) and trailing newlines match what tests scrape.

### Other helpers

After the refactor, run:

```bash
grep -n "_first_or_empty\|_warn_if_legacy_metric" cognitive_castle/searcher.py
```

If either helper is no longer referenced by any remaining function in `searcher.py`, delete it. If `search_memories` or `_new_pipeline_search` still uses them, leave them.

### `tests/test_searcher.py`

Existing CLI tests that scrape stdout for `Results for: "..."` and the per-result format continue passing because the layout is preserved.

Add one new test confirming `search()` invokes `_new_pipeline_search`:

```python
def test_cli_search_routes_through_new_pipeline(tmp_path, monkeypatch, capsys):
    """`castle search` (CLI) goes through the 3-stage pipeline, not legacy vector-only."""
    from unittest.mock import patch
    from cognitive_castle.searcher import search

    fake_hits = [
        {"id": "d1", "text": "foo", "score": 0.9, "wing": "w", "room": "r", "source_file": "f.md"},
    ]
    with patch("cognitive_castle.searcher._new_pipeline_search", return_value=fake_hits) as mock_pipeline:
        search("test query", str(tmp_path / "palace"), n_results=5)

    # Confirm the pipeline was called with is_hook_call=False.
    mock_pipeline.assert_called_once()
    kwargs = mock_pipeline.call_args.kwargs
    assert kwargs.get("is_hook_call") is False

    # Confirm the printed output uses score= (not cosine=)
    captured = capsys.readouterr()
    assert "score=0.9" in captured.out
    assert "cosine=" not in captured.out
```

Existing tests that may need updating:
- `test_search_shows_cosine_score` (if it exists) — rename to `test_search_shows_score` and update the expected substring.
- Any test asserting "cosine=" literal in the output — update to "score=".

Walk `grep -n "cosine=" tests/` at implementation time to find the exact list. Likely 1–3 tests.

## Testing strategy

1. Run new test `test_cli_search_routes_through_new_pipeline` — pass.
2. Run pre-existing `tests/test_searcher.py` — pass (with updates to any "cosine=" assertions).
3. Run focused suite regression — same failed/passed count as pre-PR baseline (215 failed, 1277 passed).
4. Manual smoke (optional): `castle init` a small palace, `castle mine`, `castle search "..."`, confirm output format and that reranker score shows up.

## Failure modes

| Failure | Surface | Handling |
|---|---|---|
| `_new_pipeline_search` raises (palace missing, model not cached, etc.) | `try/except` re-raises as `SearchError` after printing the error message. | Preserves existing CLI error UX. |
| Empty results | Print "No results found for: ..." (same message as legacy). | Preserved. |
| Result dict missing expected keys | `.get()` defaults to safe values (`"?"` for wing/room, `0.0` for score, empty string for text). | Defensive; should not happen in practice since the pipeline guarantees the schema. |

## Open questions

None substantive. The pipeline's return shape (`hits` as a `list[dict]` or wrapped in `{"results": [...]}`) varies per implementation history — check at implementation time which shape `_new_pipeline_search` actually returns and unwrap accordingly. PR #4's commit added a `"text"` alias to `"document"` per the Task 15 fix; using `.get("text") or .get("document", "")` handles both cases.

## Risk

- **Low.** Single-file change to a print-only function. Result quality should improve (reranker beats vector-only). Existing tests scraping stdout keep working as long as the layout is preserved.
- **Reversible:** `git revert` brings back vector-only CLI.
- **Net regression risk:** zero new test failures expected (existing tests scrape format, not score values).

## Acceptance criteria

1. `search()` body calls `_new_pipeline_search(..., is_hook_call=False)`.
2. CLI output uses `score=` label (not `cosine=`).
3. CLI output header (`Results for: ...`, optional Wing/Room lines, `=` separator), per-result format ([N] wing / room / Source / Match / text / `─` separator), and "No results" message preserved.
4. New test `test_cli_search_routes_through_new_pipeline` passes.
5. Existing `tests/test_searcher.py` passes (with updates to any "cosine=" string assertions).
6. Full focused regression: no new failures vs current baseline (215 failed, 1277 passed).
7. `grep -n "col.query\|col\.query" cognitive_castle/searcher.py` in `search()` body shows zero matches (the direct LanceDB query call is gone from the CLI path).
8. `git status` clean after a test suite run.
