"""
soar_bridge.py — Drive the SOAR kernel over retrieved memories.

Flow:
  1. Push retrieved memories as WMEs onto the SOAR input-link.
  2. Run 5 elaboration cycles — productions fire and annotate each memory
     with ^boost-tag WMEs.
  3. Read boost-tags back from working memory.
  4. Map tags → numeric multipliers (BOOST_MAP) and return per-memory boosts.
  5. Also read the output-link for operator signals (widen-search, create-chunk).

SOAR rules live in cognitive_castle/rules/*.soar.
SOAR binary lives at ~/.echelon/soar/bin/ (patched to use Homebrew Python 3.12).
"""

from __future__ import annotations

import datetime
import logging
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Evaluated lazily so tests that redirect HOME don't break path resolution.
def _soar_bin() -> Path:
    return Path.home() / ".echelon/soar/bin"

RULES_DIR  = Path(__file__).parent / "rules"

# Maps boost-tag values (written by SOAR productions) to numeric multipliers.
# The Python side owns the numbers; SOAR owns the symbolic classification.
BOOST_MAP: dict[str, float] = {
    "correction-same-project": 3.0,
    "procedural":              1.5,
    "deployment":              1.4,
    "user-preference":         1.3,
    "architecture":            1.2,
    "recent-access":           1.2,
    "high-access":             1.1,
    "stale":                   0.5,
    "cross-project":           0.8,
}


# ---------------------------------------------------------------------------
# SML import — lazy, path-injected
# ---------------------------------------------------------------------------

_sml = None


def _load_sml():
    global _sml
    if _sml is not None:
        return _sml
    soar_bin = _soar_bin()
    if str(soar_bin) not in sys.path:
        sys.path.insert(0, str(soar_bin))
    try:
        import Python_sml_ClientInterface as sml  # noqa: N813
        _sml = sml
        return sml
    except ImportError as exc:
        raise ImportError(
            f"SOAR SML bindings not found at {soar_bin}. "
            "Install SOAR from https://soar.eecs.umich.edu/downloads/soar/latest/ "
            f"and ensure {soar_bin} exists."
        ) from exc


# ---------------------------------------------------------------------------
# Bridge entry point
# ---------------------------------------------------------------------------


def run_soar_reasoning(
    memories: list,
    query: str,
    project_id: str,
    top_score: float = 0.0,
) -> tuple[dict[str, float], list[str]]:
    """Run SOAR production rules over a list of retrieved memories.

    Parameters
    ----------
    memories    : list of Memory objects (or dicts with the same fields)
    query       : the current retrieval query string
    project_id  : castle project identifier (e.g. "ru-sixth-sense")
    top_score   : the highest retrieval score among the memories (for impasse detection)

    Returns
    -------
    boost_map   : {memory_id -> multiplier} — multiply into existing scores
    actions     : list of output-link action strings, e.g. ["widen-search", "create-chunk"]
    """
    sml = _load_sml()

    kernel = sml.Kernel.CreateKernelInCurrentThread()
    try:
        agent  = kernel.CreateAgent("castle-agent")

        # Load all .soar rule files
        for rule_file in sorted(RULES_DIR.glob("*.soar")):
            ok = agent.LoadProductions(str(rule_file))
            if not ok:
                err = agent.GetLastErrorDescription()
                logger.warning("SOAR: failed to load %s: %s", rule_file.name, err)
            else:
                logger.debug("SOAR: loaded %s", rule_file.name)

        # ── Build input-link ───────────────────────────────────────────────
        il = agent.GetInputLink()

        # Context WMEs
        ctx = il.CreateIdWME("context")
        ctx.CreateStringWME("project", project_id or "default")
        ctx.CreateStringWME("query",   (query or "")[:200])
        il.CreateFloatWME("best-score", float(top_score))

        # One WME subtree per memory
        now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()

        for mem in memories:
            mem_id   = _attr(mem, "id",             "unknown")
            mem_type = _attr(mem, "type",            "semantic")
            subtype  = _attr(mem, "subtype",         "")
            proj     = _attr(mem, "project_id",      "")
            score    = float(_attr(mem, "_score",      0.5))
            decay    = float(_attr(mem, "decay_score", 1.0))
            access   = int(_attr(mem, "access_count",  0))
            last_acc = _attr(mem, "last_accessed_at",  None)

            recent = _was_recently_accessed(last_acc, now_ts)

            m = il.CreateIdWME("memory")
            m.CreateStringWME("id",               str(mem_id))
            m.CreateStringWME("type",             str(mem_type))
            m.CreateStringWME("subtype",          str(subtype) if subtype else "")
            m.CreateStringWME("project",          str(proj))
            m.CreateFloatWME("score",             score)
            m.CreateFloatWME("decay",             decay)
            m.CreateIntWME("access-count",        access)
            m.CreateStringWME("recently-accessed", "true" if recent else "false")

        agent.Commit()

        # ── Run decision cycles ────────────────────────────────────────────
        # 5 cycles: 1 for input elaboration, 1-2 for boost proposals,
        # 1 for operator selection, 1 for apply + output-link writes.
        agent.RunSelf(5)

        # ── Read boost-tags and actions from the output-link ──────────────
        # Productions cannot be read via Python SML Identifier.GetChild()
        # because that API only tracks WMEs created by Python, not by SOAR
        # productions. castle*elaborate*report-boost writes every
        # (memory-id, tag) pair to the output-link as:
        #   ^boost <b>  where  <b> ^memory-id <id>  ^tag <tag>
        boost_map: dict[str, float] = {}
        actions: list[str] = []

        ol = agent.GetOutputLink()
        n_ol = ol.GetNumberChildren()
        for i in range(n_ol):
            wme = ol.GetChild(i)
            if not wme:
                continue
            attr = wme.GetAttribute()

            if attr == "boost":
                boost_id = wme.ConvertToIdentifier()
                if not boost_id:
                    continue
                mem_id_val: Optional[str] = None
                tag_val: Optional[str] = None
                for j in range(boost_id.GetNumberChildren()):
                    sub = boost_id.GetChild(j)
                    if not sub:
                        continue
                    if sub.GetAttribute() == "memory-id":
                        mem_id_val = sub.GetValueAsString()
                    elif sub.GetAttribute() == "tag":
                        tag_val = sub.GetValueAsString()
                if mem_id_val and tag_val:
                    multiplier = BOOST_MAP.get(tag_val, 1.0)
                    boost_map[mem_id_val] = boost_map.get(mem_id_val, 1.0) * multiplier
                    logger.debug(
                        "SOAR: memory %s tagged %s (×%.1f)", mem_id_val, tag_val, multiplier
                    )

            elif attr == "action":
                actions.append(wme.GetValueAsString())

    finally:
        kernel.Shutdown()

    return boost_map, actions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _attr(obj, name: str, default):
    """Get attribute from object or dict."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _was_recently_accessed(last_acc, now_ts: float, window_s: float = 86400.0) -> bool:
    if not last_acc:
        return False
    try:
        ts = datetime.datetime.fromisoformat(str(last_acc)).timestamp()
        return (now_ts - ts) < window_s
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Convenience: apply SOAR boosts to a scored memory list
# ---------------------------------------------------------------------------


def apply_soar_boosts(
    scored_memories: list,
    query: str,
    project_id: str,
) -> list:
    """Re-rank a list of scored Memory objects using SOAR production rules.

    Each item in scored_memories must have a ``_score`` attribute/key.
    Returns the same list, sorted descending by SOAR-boosted score.
    """
    if not scored_memories:
        return scored_memories

    top_score = max(float(_attr(m, "_score", 0.0)) for m in scored_memories)

    try:
        boost_map, actions = run_soar_reasoning(
            scored_memories, query, project_id, top_score
        )
    except Exception:
        logger.exception("SOAR reasoning failed — returning un-boosted scores")
        return scored_memories

    if "widen-search" in actions:
        logger.info("SOAR: impasse detected — caller should widen search via graph")

    if "create-chunk" in actions:
        logger.info("SOAR: chunk candidate detected — consider compressing repeated memories")

    # Apply boosts
    for mem in scored_memories:
        mem_id  = str(_attr(mem, "id", ""))
        boost   = boost_map.get(mem_id, 1.0)
        old     = float(_attr(mem, "_score", 0.0))
        new     = old * boost
        if isinstance(mem, dict):
            mem["_score"] = new
            mem["_soar_boost"] = boost
        else:
            mem._score      = new
            mem._soar_boost = boost

    scored_memories.sort(key=lambda m: float(_attr(m, "_score", 0.0)), reverse=True)
    return scored_memories
