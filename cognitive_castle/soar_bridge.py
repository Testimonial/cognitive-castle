"""soar_bridge.py — SOAR post-pipeline boost-tag layer (PR #4a, experimental).

Opt-in via --mode boosted/max (or mode:boosted/max MCP).
Default behavior unchanged. Module is lazy-imported by callers so its load
cost is zero for users who never use boosted/max mode.

Soar runs ELABORATION productions over the input-link memory WMEs, adding
i-supported ^boost-tag attributes. Python reads tags back, maps via
BOOST_MULTIPLIERS, applies as multiplicative score adjustments. Audit fields
(soar_boost, soar_tags, score_pre_soar) are added to each hit so every score
change has a name — the differentiating value over neural rerankers.

EpMem + SMem subsystems are enabled at agent creation (preparation for #4c
chunking) but not READ/WRITTEN in #4a — the placeholder fields they'd
populate (^access-count, ^decay) are explicitly absent from the #4a WM
schema rather than carry stub values that could fire bad rules.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from typing import Optional


# Module-level state. Cleared by _reset_for_test() in test runs.
_KERNEL = None  # singleton kernel instance
_AGENTS: dict = {}  # palace_path → agent instance
_WARNED: set = set()  # one-time-per-process warning keys
_SML = None  # cached SML module (or None if unavailable)
_SML_LOAD_ATTEMPTED = False  # whether we've tried _load_sml() at least once
_PREV_TOP_WMES: dict = {}  # palace_path → list of top-level WME handles from last call


# Boost-tag → multiplier map. Compounded multiplicatively when multiple tags
# fire on the same hit. Final boost clamped to [0.1, 10.0] (see apply_soar_boosts).
BOOST_MULTIPLIERS: dict[str, float] = {
    "recency-boost": 1.25,  # ^recently-accessed "true" (age < 7d default)
    "same-project": 1.15,  # ^project matches ^io.input-link.context.project
    "entity-match": 1.30,  # ^entity-match "true" (came via KG-hop entity match)
    "type-match": 1.25,  # ^drawer-type matches ^io.input-link.context.query-type
}

# Hardcoded operational limits (YAGNI on promoting to config knobs).
MAX_WM_HITS = 50  # Truncate input WM if more hits than this
DECISION_CYCLES = 50  # Upper bound on agent.RunSelf cycles
RECENCY_THRESHOLD_SEC = 7 * 24 * 3600  # 7 days for "recently-accessed"
BOOST_CLAMP = (0.1, 10.0)  # Min, max for final compound multiplier

# Map drawer room names (from miners) to the singular memory_types that
# SOAR's type-match rule expects on ^drawer-type. convo_miner emits plurals
# ("decisions", "problems") via TOPIC_KEYWORDS; general_extractor emits
# singulars ("decision", "preference", …). The rule's WME schema is
# singular, so plurals are aliased here before being pushed.
_ROOM_TO_MEMORY_TYPE: dict[str, str] = {
    # Plurals from convo_miner.TOPIC_KEYWORDS
    "decisions": "decision",
    "problems": "problem",
    "preferences": "preference",
    "milestones": "milestone",
    # Singulars from general_extractor (identity mappings)
    "decision": "decision",
    "preference": "preference",
    "milestone": "milestone",
    "problem": "problem",
    "emotional": "emotional",
}


def _normalize_room_to_memory_type(room: str) -> Optional[str]:
    """Return the memory_type for a drawer room, or None if room doesn't match.

    Bridges convo_miner's plural topic rooms (e.g. "decisions") and
    general_extractor's singular memory_types (e.g. "decision") to a single
    canonical singular value matching ``query_intent.MEMORY_TYPES``.
    """
    return _ROOM_TO_MEMORY_TYPE.get(room)


def _warn_once(key: str, message: str) -> None:
    """Print a stderr warning ONCE per process for the given key."""
    if key in _WARNED:
        return
    _WARNED.add(key)
    print(f"[soar] {message}", file=sys.stderr)


def _load_sml():
    """Lazy import of Python_sml_ClientInterface. Returns the module or None.

    Respects CASTLE_SML_DISABLED=1 (testability knob) — returns None even
    when SML is importable. Caches the result in module-level _SML.
    """
    global _SML, _SML_LOAD_ATTEMPTED
    if _SML_LOAD_ATTEMPTED:
        return _SML
    _SML_LOAD_ATTEMPTED = True

    if os.environ.get("CASTLE_SML_DISABLED") == "1":
        _warn_once(
            "sml-disabled-env",
            "SML Python bindings not available (CASTLE_SML_DISABLED=1) — install Soar 9.6+ with SML, or use --mode fast/standard to skip SOAR Stage 5",
        )
        return None

    try:
        import Python_sml_ClientInterface as sml  # type: ignore

        _SML = sml
        return sml
    except ImportError:
        _warn_once(
            "sml-import-failed",
            "SML Python bindings not available — install Soar 9.6+ with SML, or use --mode fast/standard to skip SOAR Stage 5",
        )
        return None


def _reset_for_test() -> None:
    """Test-only helper: clear all module-level state.

    Used by the autouse `reset_soar_state` fixture in test_soar_bridge.py
    so sequential tests don't share kernel/agent state. NOT for production use.
    """
    global _KERNEL, _SML, _SML_LOAD_ATTEMPTED
    # Properly destroy any existing agents + kernel before nulling refs.
    if _KERNEL is not None:
        try:
            for agent in _AGENTS.values():
                _KERNEL.DestroyAgent(agent)
        except Exception:
            pass
        try:
            _KERNEL.Shutdown()
        except Exception:
            pass
    _AGENTS.clear()
    _PREV_TOP_WMES.clear()
    _KERNEL = None
    _SML = None
    _SML_LOAD_ATTEMPTED = False
    _WARNED.clear()


def _get_kernel():
    """Return the singleton Soar kernel, creating it on first call."""
    global _KERNEL
    if _KERNEL is None:
        sml = _load_sml()
        if sml is None:
            return None
        try:
            _KERNEL = sml.Kernel.CreateKernelInNewThread()
        except Exception as e:
            _warn_once(
                "kernel-create-failed",
                f"kernel creation failed ({type(e).__name__}: {e}): boost-tags skipped",
            )
            return None
    return _KERNEL


def _get_agent(palace_path: str, rules_path: str):
    """Return the per-palace agent. First-time creation loads productions
    and enables EpMem + SMem subsystems.

    Returns None on any failure (stderr warning emitted).
    """
    if palace_path in _AGENTS:
        return _AGENTS[palace_path]

    kernel = _get_kernel()
    if kernel is None:
        return None

    # Agent name must be unique per kernel + safe characters
    agent_name = f"castle-{abs(hash(palace_path)) % 100_000_000}"
    try:
        agent = kernel.CreateAgent(agent_name)
    except Exception as e:
        _warn_once(
            "agent-create-failed",
            f"agent creation failed ({type(e).__name__}: {e}): boost-tags skipped",
        )
        return None

    # Load productions
    if rules_path is None or not os.path.exists(rules_path):
        _warn_once(
            f"rules-not-found-{rules_path}",
            f"rule file not found: {rules_path}",
        )
        kernel.DestroyAgent(agent)
        return None

    try:
        # LoadProductions returns a Python bool in Soar 9.6.40: True on
        # success, False on syntax / parse error. The actual error text
        # is in GetLastCommandLineResult() when False.
        ok = agent.LoadProductions(rules_path)
        if not ok:
            err_msg = ""
            if hasattr(agent, "GetLastCommandLineResult"):
                err_msg = str(agent.GetLastCommandLineResult())
            _warn_once(
                "rules-parse-failure",
                f"rule parse failure ({rules_path}): {err_msg or 'unknown'}",
            )
            kernel.DestroyAgent(agent)
            return None
    except Exception as e:
        _warn_once(
            "rules-load-failed",
            f"rule load failed ({type(e).__name__}: {e})",
        )
        kernel.DestroyAgent(agent)
        return None

    # Enable EpMem + SMem subsystems (PR #4c will use them; #4a just configures)
    try:
        agent.ExecuteCommandLine("epmem --set learning on")
        agent.ExecuteCommandLine("smem --set learning on")
    except Exception:
        # Non-fatal — log but don't fail
        _warn_once(
            "epmem-smem-config-failed",
            "EpMem/SMem subsystem configuration failed (boost-tags still work)",
        )

    _AGENTS[palace_path] = agent
    return agent


def _push_working_memory(agent, hits: list[dict], query: str = "") -> tuple[dict, list]:
    """Push hits + context to SOAR's working memory.

    Builds ^io.input-link structure:
      ^io.input-link <il>
      <il>           ^context <ctx>
                     ^memory[]  with id, project, score, age-seconds,
                                recently-accessed, entity-match, drawer-type
      ^context <ctx> ^project <string>
                     [^query-type <string>]   ← when classify_query succeeds
      ^memory <m>    [^drawer-type <string>]  ← when hit.room in MEMORY_TYPES

    query is classified via cognitive_castle.query_intent.classify_query;
    if it returns one of the 5 memory_types, ^context.query-type is pushed.
    For each hit, if its room is one of the 5 known memory_types,
    ^memory.drawer-type is pushed. The castle-boost*type-match rule fires
    when both attributes match.

    Returns (memory_wmes, top_level_wmes) for later WM cleanup.
    """
    # ── Import here (NOT module-level) to keep query_intent only loaded when SOAR fires ──
    from .query_intent import classify_query

    input_link = agent.GetInputLink()
    project = os.environ.get("CASTLE_PROJECT", "default")

    top_level_wmes = []

    # Push context
    context_wme = input_link.CreateIdWME("context")
    context_wme.CreateStringWME("project", project)

    # ── NEW (PR #4c-type-match): push ^context.query-type when classification succeeds ──
    # classify_query handles empty/whitespace/non-matching internally — returns None.
    query_type = classify_query(query)
    if query_type:
        context_wme.CreateStringWME("query-type", query_type)
    # If query_type is None, skip the push — rule can't fire without it.

    top_level_wmes.append(context_wme)

    # Push one ^memory WME per hit
    memory_wmes = {}  # composite_id → WME handle
    now = time.time()
    for hit in hits:
        m = input_link.CreateIdWME("memory")
        composite_id = f"{hit.get('wing', '')}/{hit.get('room', '')}/{hit.get('source_file', '?')}"
        m.CreateStringWME("id", composite_id)
        m.CreateStringWME("project", hit.get("wing", ""))
        m.CreateFloatWME("score", float(hit.get("score", 0.0)))

        # Compute age-seconds from created_at if present
        age_sec = _compute_age_seconds(hit.get("created_at"), now)
        # Cap infinity (missing created_at) to a large int Soar can represent
        age_sec_int = int(min(age_sec, 2**62)) if age_sec != float("inf") else 2**62
        m.CreateIntWME("age-seconds", age_sec_int)

        # ^recently-accessed: "true" (string symbol — Soar matches `^recently-accessed true`)
        recent = "true" if age_sec < RECENCY_THRESHOLD_SEC else "false"
        m.CreateStringWME("recently-accessed", recent)

        # ^entity-match: "true" if hit came via KG-hop (fusion provenance flag),
        # else "false". String symbol to match the recently-accessed pattern.
        entity_match = "true" if hit.get("entity_match") else "false"
        m.CreateStringWME("entity-match", entity_match)

        # ── PR #4c-type-match: push ^memory.drawer-type when room maps to a memory_type ──
        # convo_miner uses plural room names ("decisions", "problems"), while
        # general_extractor uses singular memory_types. _normalize_room_to_memory_type
        # bridges both schemes so type-match fires regardless of which miner produced
        # the drawer.
        memory_type = _normalize_room_to_memory_type(hit.get("room") or "")
        if memory_type:
            m.CreateStringWME("drawer-type", memory_type)
        # If room doesn't map to a memory_type, skip — rule can't fire for this hit.

        memory_wmes[composite_id] = m
        top_level_wmes.append(m)

    agent.Commit()
    return memory_wmes, top_level_wmes


def _compute_age_seconds(created_at_iso: Optional[str], now: float) -> float:
    """Compute age in seconds from ISO timestamp. Returns large value if missing/invalid.

    Handles ``"2026-05-13T00:00:00Z"`` (UTC, "Z" suffix) and
    ``"2026-05-13T00:00:00"`` (naive — assumed UTC for our purposes).
    """
    if not created_at_iso:
        return float("inf")
    try:
        # Convert "Z" suffix to "+00:00" so fromisoformat parses as
        # timezone-aware UTC. `rstrip("Z")` is wrong because it would
        # strip the Z but leave the datetime naive (interpreted as local
        # time by .timestamp()) — fine for naive timestamps but breaks
        # for UTC-suffixed ones on non-UTC systems.
        ts = (
            created_at_iso.replace("Z", "+00:00")
            if created_at_iso.endswith("Z")
            else created_at_iso
        )
        dt = datetime.fromisoformat(ts)
        return max(0.0, now - dt.timestamp())
    except (ValueError, TypeError):
        return float("inf")


def _read_boost_tags(agent, _memory_wmes_unused: dict) -> dict:
    """Read back ^boost-tag attributes from each ^memory WME. Returns composite_id → list[tag].

    SML Python bindings only expose client-created WMEs via GetNumberChildren/GetChild;
    server-side elaborated WMEs (like i-supported ^boost-tag) are invisible there.
    We use ExecuteCommandLine("print --depth 4 i2") and parse its text output instead.
    """
    import re

    raw = agent.ExecuteCommandLine("print --depth 4 i2")

    # Merge continuation lines into single-line blocks
    merged_lines = []
    buf = ""
    for line in raw.split("\n"):
        stripped = line.strip()
        if not stripped:
            if buf:
                merged_lines.append(buf)
                buf = ""
            continue
        if stripped.startswith("("):
            if buf:
                merged_lines.append(buf)
            buf = stripped
        else:
            buf = (buf + " " + stripped) if buf else stripped
    if buf:
        merged_lines.append(buf)

    # Parse each line: (SYM ^attr val ^attr val ...)
    blocks: dict[str, dict[str, list[str]]] = {}
    for line in merged_lines:
        m = re.match(r"\(([A-Z]\d+)\s*(.*)\)\s*$", line, re.DOTALL)
        if not m:
            continue
        sym = m.group(1)
        rest = m.group(2)
        blocks[sym] = {}
        # Match ^attr val pairs; val is either |quoted string| or bare word/identifier
        for attr_match in re.finditer(r"\^(\S+)\s+(\|[^|]*\||\S+)", rest):
            attr = attr_match.group(1)
            val = attr_match.group(2).strip("|")
            blocks[sym].setdefault(attr, []).append(val)

    # Build composite_id → tags mapping using the ^id attribute
    tags_by_id: dict[str, list[str]] = {}
    for _sym, attrs in blocks.items():
        if "id" in attrs:
            composite_id = attrs["id"][0]
            tags_by_id[composite_id] = attrs.get("boost-tag", [])

    return tags_by_id


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _annotate_unboosted(hits: list[dict]) -> list[dict]:
    """Annotate hits with neutral audit fields (no boost applied)."""
    for h in hits:
        h.setdefault("score_pre_soar", h.get("score", 0.0))
        h.setdefault("soar_boost", 1.0)
        h.setdefault("soar_tags", [])
    return hits


def apply_soar_boosts(hits: list[dict], cfg, query: str = "") -> list[dict]:
    """Post-pipeline boost-tag application.

    Args:
        hits: Search hits (typically from search_memories() result["results"]).
            Each hit must have at least: "id", "score", "wing", and optionally
            "created_at" (used to derive recency).
        cfg: Config object exposing .soar_rules_path, .palace_path.
        query: The original search query string. Forwarded to
            _push_working_memory so the type-match rule (PR #4c-type-match)
            can classify it into a memory_type intent. Default empty preserves
            back-compat for external callers that don't have the query handy.

    Returns:
        list[dict]: same hits with `score` adjusted by SOAR's compound multiplier
        and 3 new audit-trail fields appended to each hit:
        - soar_boost: float — the compound multiplier applied (1.0 if no tags fired)
        - soar_tags: list[str] — names of boost-tag rules that fired
        - score_pre_soar: float — original score before adjustment

    Never raises. Search continues with degraded behavior on Soar failure.
    On any failure (SML missing, kernel/agent/rules error,
    truncation, unknown tag, etc.) prints a one-time-per-process stderr
    warning and returns hits unchanged (or partially boosted).
    """
    # Lazy SML import
    sml = _load_sml()
    if sml is None:
        _warn_once(
            "sml-unavailable",
            "SML Python bindings not available — install Soar 9.6+ with SML, or use --mode fast/standard to skip SOAR Stage 5",
        )
        # Return hits with neutral audit fields so downstream callers can
        # always rely on `soar_tags` / `soar_boost` / `score_pre_soar` being
        # present, regardless of whether SOAR ran. Matches the agent-init
        # failure branch below.
        return _annotate_unboosted(hits)

    # Empty input → fast path
    if not hits:
        return hits

    # Truncate to MAX_WM_HITS if needed
    truncated_remainder = []
    if len(hits) > MAX_WM_HITS:
        truncated_remainder = hits[MAX_WM_HITS:]
        _warn_once(
            "wm-truncated",
            f"truncated WM to {MAX_WM_HITS} hits (input was {len(hits)}); remainder unboosted",
        )
        hits = hits[:MAX_WM_HITS]

    # Get agent (lazy-init per palace)
    agent = _get_agent(cfg.palace_path, cfg.soar_rules_path)
    if agent is None:
        # Failure already logged; return hits with neutral audit fields
        return _annotate_unboosted(hits + truncated_remainder)

    # Clear prior WM: destroy the top-level WMEs pushed by the previous call.
    # SML tracks client-side WMEs across calls; destroying them (then Commit) removes
    # them from Soar's WM so they don't leak into the next decision cycle.
    palace_key = cfg.palace_path
    prev_wmes = _PREV_TOP_WMES.get(palace_key, [])
    if prev_wmes:
        try:
            for wme in prev_wmes:
                agent.DestroyWME(wme)
            agent.Commit()
        except Exception as e:
            _warn_once("wm-clear-failed", f"WM clear failed ({type(e).__name__}: {e})")
            return _annotate_unboosted(hits + truncated_remainder)

    # Build composite_id keys for hit lookup
    composite_ids = [
        f"{h.get('wing', '')}/{h.get('room', '')}/{h.get('source_file', '?')}" for h in hits
    ]

    # Push WM
    try:
        memory_wmes, top_level_wmes = _push_working_memory(agent, hits, query=query)
    except Exception as e:
        _warn_once("wm-push-failed", f"WM push failed ({type(e).__name__}: {e})")
        return _annotate_unboosted(hits + truncated_remainder)

    # Store top-level WMEs for cleanup on next call
    _PREV_TOP_WMES[palace_key] = top_level_wmes

    # Run decision cycle
    try:
        agent.RunSelf(DECISION_CYCLES)
    except Exception as e:
        _warn_once("decision-cycle-failed", f"decision cycle failed ({type(e).__name__}: {e})")
        return _annotate_unboosted(hits + truncated_remainder)

    # Read back tags
    try:
        tags_by_id = _read_boost_tags(agent, memory_wmes)
    except Exception as e:
        _warn_once("read-tags-failed", f"read-tags failed ({type(e).__name__}: {e})")
        return _annotate_unboosted(hits + truncated_remainder)

    # Apply multipliers + augment audit fields
    any_tags_fired = False
    for hit, cid in zip(hits, composite_ids):
        tags = tags_by_id.get(cid, [])
        recognized = []
        compound = 1.0
        for tag in tags:
            mul = BOOST_MULTIPLIERS.get(tag)
            if mul is None:
                _warn_once(
                    f"unknown-tag-{tag}",
                    f"unknown boost-tag '{tag}' — add to BOOST_MULTIPLIERS or check rule output",
                )
                continue
            compound *= mul
            recognized.append(tag)
        compound = _clamp(compound, *BOOST_CLAMP)
        if recognized:
            any_tags_fired = True
        hit["score_pre_soar"] = hit["score"]
        hit["soar_boost"] = compound
        hit["soar_tags"] = recognized
        hit["score"] = hit["score"] * compound

    if not any_tags_fired:
        # Not an error — just informational. Don't warn-once because empty rule
        # files are a legitimate test case.
        pass

    # Combine boosted hits with truncated remainder
    return hits + _annotate_unboosted(truncated_remainder)


def _extract_filed_at(row: dict) -> str:
    """Parse filed_at out of a raw-pipeline row's metadata_json JSON blob.

    Mirrors searcher._get_filed_at but inlined here to avoid a circular import
    (searcher already lazy-imports soar_bridge). Returns "" when filed_at is
    missing, metadata_json is missing/non-string, or JSON is malformed.
    """
    raw = row.get("metadata_json")
    if not isinstance(raw, str):
        return ""
    try:
        return str(json.loads(raw).get("filed_at", ""))
    except (json.JSONDecodeError, TypeError):
        return ""


def _apply_soar_to_reranked(
    reranked: list[tuple[float, dict]],
    cfg,
    query: str = "",
) -> list[tuple[float, dict]]:
    """Apply SOAR boost-tags to a list of (score, row) tuples.

    Equivalent to apply_soar_boosts() but operates on the tuple shape used
    inside _new_pipeline_search. Returns a NEW list sorted by boosted score
    (descending). Each row dict is mutated in place with audit-trail fields
    (soar_boost, soar_tags, score_pre_soar) so they surface in the final hits.

    The query string is forwarded to apply_soar_boosts so the type-match
    rule (PR #4c-type-match) can use it.

    Never raises. Same graceful-fallback behavior as apply_soar_boosts.
    """
    if not reranked:
        return reranked

    # Adapt tuples → dict shape for the shared rule-firing core.
    # Each tuple's row dict already has the fields apply_soar_boosts reads.
    # Set "score" on each row from the tuple (the tuple's score is the
    # authoritative pre-SOAR score, regardless of any "score" already on the row).
    hits_view = []
    for score, row in reranked:
        row["score"] = score
        # Pipeline rows carry filed_at inside metadata_json (JSON blob) but
        # apply_soar_boosts reads hit["created_at"] for recency. Without this
        # promotion, recency-boost never fires on raw-pipeline rows.
        if not row.get("created_at"):
            row["created_at"] = _extract_filed_at(row)
        hits_view.append(row)

    # Delegate to the existing public API; it mutates hits_view in place
    # (sets soar_boost, soar_tags, score_pre_soar and updates "score").
    boosted = apply_soar_boosts(hits_view, cfg, query=query)

    # Guarantee audit-trail fields on every row even when apply_soar_boosts
    # returned early (SML unavailable, kill-switch, etc.) without annotating.
    _annotate_unboosted(boosted)

    # Rebuild tuples from the (possibly mutated) row dicts using updated scores.
    new_tuples = [(h["score"], h) for h in boosted]
    new_tuples.sort(key=lambda t: -t[0])
    return new_tuples
