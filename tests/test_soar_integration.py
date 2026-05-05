"""
test_soar_integration.py — End-to-end tests for the SOAR re-ranking pipeline.

Verifies that:
  1. soar_bridge.run_soar_reasoning fires the correct production rules and
     returns the expected boost multipliers via the output-link.
  2. apply_soar_boosts re-sorts a memory list correctly.
  3. tool_search returns soar_boost / soar_score fields and re-ranks results
     when the SOAR bindings are available; degrades gracefully when they are not.
"""

import glob as _glob_mod
import os
import tempfile
import shutil
from pathlib import Path
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _soar_available() -> bool:
    """Return True only if the SOAR SML bindings can actually be loaded.

    Uses REAL_HOME env var (set by conftest before HOME is redirected) when
    available, falling back to /proc/$PPID/environ or a direct glob so the
    check works even when pytest's conftest has redirected HOME to a tmpdir.
    """
    # Try to find the .so / .pyd regardless of what HOME is currently set to.
    # The real user home is the parent of the first /Users/* or /home/* entry.
    candidates = [
        # Explicit override — set in conftest if needed
        os.environ.get("SOAR_BIN_PATH", ""),
        # Typical macOS location
        "/Users/ladislavbihari/.echelon/soar/bin",
        # Generic: any ~-expanded path (works when HOME is real)
        str(Path.home() / ".echelon/soar/bin"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if _glob_mod.glob(os.path.join(candidate, "Python_sml_ClientInterface*")):
            return True
    return False


SOAR_SKIP = pytest.mark.skipif(
    not _soar_available(),
    reason="SOAR SML bindings not installed at ~/.echelon/soar/bin",
)


# ---------------------------------------------------------------------------
# Shared: restore real SOAR_BIN path (conftest may have changed HOME)
# ---------------------------------------------------------------------------

_REAL_SOAR_BIN = "/Users/ladislavbihari/.echelon/soar/bin"


@pytest.fixture(autouse=False)
def _real_soar_bin(monkeypatch):
    """Patch soar_bridge._soar_bin() to return the real path regardless of HOME."""
    import cognitive_castle.soar_bridge as _sb
    monkeypatch.setattr(_sb, "_soar_bin", lambda: Path(_REAL_SOAR_BIN))
    # Also reset the cached _sml so it re-imports using the correct path.
    original_sml = _sb._sml
    _sb._sml = None
    yield
    _sb._sml = original_sml


# ---------------------------------------------------------------------------
# Unit: soar_bridge.run_soar_reasoning
# ---------------------------------------------------------------------------


@SOAR_SKIP
class TestRunSoarReasoning:
    @pytest.fixture(autouse=True)
    def _fix_soar_path(self, _real_soar_bin):
        pass

    def _memories(self):
        return [
            {
                "id": "mem-correction",
                "type": "semantic",
                "subtype": "correction",
                "project_id": "test-project",
                "_score": 0.80,
                "decay_score": 1.0,
                "access_count": 6,
                "last_accessed_at": None,
            },
            {
                "id": "mem-procedural",
                "type": "procedural",
                "subtype": "",
                "project_id": "test-project",
                "_score": 0.70,
                "decay_score": 1.0,
                "access_count": 2,
                "last_accessed_at": None,
            },
            {
                "id": "mem-stale-cross",
                "type": "semantic",
                "subtype": "",
                "project_id": "other-project",
                "_score": 0.60,
                "decay_score": 0.1,
                "access_count": 1,
                "last_accessed_at": None,
            },
        ]

    def test_correction_same_project_gets_highest_boost(self):
        from cognitive_castle.soar_bridge import run_soar_reasoning

        boost_map, _ = run_soar_reasoning(
            self._memories(), "some query", "test-project", top_score=0.80
        )
        # correction-same-project(×3.0) × high-access(×1.1) = 3.3
        assert boost_map["mem-correction"] == pytest.approx(3.3, rel=0.01)

    def test_procedural_gets_1_5_boost(self):
        from cognitive_castle.soar_bridge import run_soar_reasoning

        boost_map, _ = run_soar_reasoning(
            self._memories(), "some query", "test-project", top_score=0.80
        )
        assert boost_map["mem-procedural"] == pytest.approx(1.5, rel=0.01)

    def test_stale_cross_project_gets_penalty(self):
        from cognitive_castle.soar_bridge import run_soar_reasoning

        boost_map, _ = run_soar_reasoning(
            self._memories(), "some query", "test-project", top_score=0.80
        )
        # stale(×0.5) × cross-project(×0.8) = 0.4
        assert boost_map["mem-stale-cross"] == pytest.approx(0.4, rel=0.01)

    def test_low_confidence_returns_widen_search_action(self):
        from cognitive_castle.soar_bridge import run_soar_reasoning

        _, actions = run_soar_reasoning(
            self._memories(), "obscure query", "test-project", top_score=0.10
        )
        assert "widen-search" in actions

    def test_normal_confidence_returns_summarise_action(self):
        from cognitive_castle.soar_bridge import run_soar_reasoning

        _, actions = run_soar_reasoning(
            self._memories(), "query", "test-project", top_score=0.80
        )
        assert "summarise-context" in actions

    def test_empty_memories_returns_empty_boost_map(self):
        from cognitive_castle.soar_bridge import run_soar_reasoning

        boost_map, actions = run_soar_reasoning([], "query", "test-project")
        assert boost_map == {}

    def test_user_type_gets_user_preference_boost(self):
        from cognitive_castle.soar_bridge import run_soar_reasoning

        mems = [
            {
                "id": "user-pref",
                "type": "user",
                "subtype": "",
                "project_id": "test-project",
                "_score": 0.6,
                "decay_score": 1.0,
                "access_count": 0,
                "last_accessed_at": None,
            }
        ]
        boost_map, _ = run_soar_reasoning(mems, "q", "test-project", top_score=0.6)
        assert boost_map["user-pref"] == pytest.approx(1.3, rel=0.01)


# ---------------------------------------------------------------------------
# Unit: apply_soar_boosts — sorting contract
# ---------------------------------------------------------------------------


@SOAR_SKIP
class TestApplySoarBoosts:
    @pytest.fixture(autouse=True)
    def _fix_soar_path(self, _real_soar_bin):
        pass

    def test_correction_overtakes_higher_similarity_doc(self):
        """A correction memory should rise above a higher-similarity generic doc."""
        from cognitive_castle.soar_bridge import apply_soar_boosts

        mems = [
            {"id": "generic",    "type": "semantic",  "subtype": "",           "project_id": "p", "_score": 0.90, "decay_score": 1.0, "access_count": 0, "last_accessed_at": None},
            {"id": "correction", "type": "semantic",  "subtype": "correction", "project_id": "p", "_score": 0.70, "decay_score": 1.0, "access_count": 0, "last_accessed_at": None},
        ]
        result = apply_soar_boosts(mems, "query", "p")
        assert result[0]["id"] == "correction"

    def test_stale_sinks_to_bottom(self):
        from cognitive_castle.soar_bridge import apply_soar_boosts

        mems = [
            {"id": "fresh", "type": "semantic", "subtype": "", "project_id": "p", "_score": 0.60, "decay_score": 1.0, "access_count": 0, "last_accessed_at": None},
            {"id": "stale", "type": "semantic", "subtype": "", "project_id": "p", "_score": 0.70, "decay_score": 0.1, "access_count": 0, "last_accessed_at": None},
        ]
        result = apply_soar_boosts(mems, "query", "p")
        assert result[-1]["id"] == "stale"

    def test_soar_boost_attached_to_each_memory(self):
        from cognitive_castle.soar_bridge import apply_soar_boosts

        mems = [{"id": "x", "type": "semantic", "subtype": "", "project_id": "p", "_score": 0.5, "decay_score": 1.0, "access_count": 0, "last_accessed_at": None}]
        result = apply_soar_boosts(mems, "q", "p")
        assert "_soar_boost" in result[0]

    def test_empty_list_passthrough(self):
        from cognitive_castle.soar_bridge import apply_soar_boosts

        assert apply_soar_boosts([], "q", "p") == []


# ---------------------------------------------------------------------------
# Integration: tool_search SOAR fields + ranking
# ---------------------------------------------------------------------------


@SOAR_SKIP
class TestToolSearchSoarIntegration:
    """Seed a real LanceDB palace and assert tool_search re-ranks via SOAR."""

    @pytest.fixture(autouse=True)
    def _fix_soar_path(self, _real_soar_bin):
        pass

    @pytest.fixture(autouse=True)
    def _isolated_palace(self, monkeypatch, tmp_path):
        """Point mcp_server at a throwaway LanceDB palace."""
        palace = str(tmp_path / "palace")
        os.makedirs(palace)

        from cognitive_castle.config import MempalaceConfig
        from cognitive_castle.knowledge_graph import KnowledgeGraph
        from cognitive_castle import mcp_server

        cfg_dir = str(tmp_path / "cfg")
        os.makedirs(cfg_dir)
        import json
        with open(os.path.join(cfg_dir, "config.json"), "w") as f:
            json.dump({"palace_path": palace}, f)

        cfg = MempalaceConfig(config_dir=cfg_dir)
        kg  = KnowledgeGraph(db_path=str(tmp_path / "kg.sqlite3"))

        monkeypatch.setattr(mcp_server, "_config", cfg)
        monkeypatch.setattr(mcp_server, "_kg", kg)
        monkeypatch.setenv("CASTLE_PROJECT", "test-project")
        # _vector_disabled removed — LanceDB has no HNSW divergence mode

        # Seed using LanceDB directly (palace._DEFAULT_BACKEND is still Chroma).
        from cognitive_castle.backends.lancedb_backend import LanceDBBackend
        from cognitive_castle.embedding import embed_texts

        backend = LanceDBBackend()
        col = backend.get_collection(palace, collection_name="castle_drawers", create=True)

        # Also patch searcher to use LanceDB for this test.
        import cognitive_castle.palace as _palace
        monkeypatch.setattr(_palace, "_DEFAULT_BACKEND", backend)

        docs = [
            # Lower cosine similarity, but a correction from this project → should win.
            "CORRECTION: do not use set-piece restart for a lineout tap-and-go. "
            "Always call 'lineout restart' to trigger the correct qualifier.",
            # Higher semantic similarity to the query but just a generic note.
            "Lineout: the throwing team lifts a jumper to contest for possession. "
            "Common restart after the ball goes into touch.",
        ]
        ids = ["correction-lineout", "generic-lineout"]
        vecs = embed_texts(docs)
        metas = [
            {"wing": "wing_code", "room": "events",  "source_file": "correction-lineout.md", "chunk_index": 0, "added_by": "test", "filed_at": "2026-01-01T00:00:00", "decay_score": 1.0, "subtype": "correction", "project_id": "test-project"},
            {"wing": "wing_code", "room": "events",  "source_file": "generic-lineout.md",    "chunk_index": 0, "added_by": "test", "filed_at": "2026-01-01T00:00:00", "decay_score": 1.0, "subtype": "",           "project_id": "test-project"},
        ]
        col.upsert(documents=docs, ids=ids, metadatas=metas, embeddings=vecs)

        yield

        kg.close()
        # _client_cache removed — LanceDB backend has no separate client cache
        mcp_server._collection_cache = None

    def test_soar_boost_field_present(self):
        from cognitive_castle.mcp_server import tool_search

        result = tool_search(query="lineout restart qualification")
        assert result.get("soar_boosted") is True
        for hit in result["results"]:
            assert "soar_boost" in hit
            assert "soar_score" in hit

    def test_similarity_unchanged(self):
        """similarity should still be raw cosine [0, 1]; soar_score carries the boost."""
        from cognitive_castle.mcp_server import tool_search

        result = tool_search(query="lineout restart qualification")
        for hit in result["results"]:
            assert 0.0 <= hit["similarity"] <= 1.0

    def test_correction_ranks_first(self):
        """Correction from the same project must rank above a generic note."""
        from cognitive_castle.mcp_server import tool_search

        result = tool_search(query="lineout restart qualification", limit=5)
        hits = result["results"]
        ids = [h["source_file"] for h in hits]
        correction_rank = next((i for i, sid in enumerate(ids) if "correction" in sid), None)
        generic_rank    = next((i for i, sid in enumerate(ids) if "generic"    in sid), None)
        assert correction_rank is not None
        assert generic_rank    is not None
        assert correction_rank < generic_rank, (
            f"correction (rank {correction_rank}) should beat generic (rank {generic_rank})"
        )

    def test_metadata_not_in_results(self):
        """Internal metadata dict must be stripped before results reach the caller."""
        from cognitive_castle.mcp_server import tool_search

        result = tool_search(query="lineout restart")
        for hit in result["results"]:
            assert "metadata" not in hit


# ---------------------------------------------------------------------------
# Graceful degradation: SOAR unavailable
# ---------------------------------------------------------------------------


class TestSoarDegradation:
    """When SOAR bindings are absent, tool_search still returns valid results."""

    def test_search_succeeds_without_soar(self, monkeypatch, tmp_path):
        palace = str(tmp_path / "palace")
        os.makedirs(palace)

        from cognitive_castle.config import MempalaceConfig
        from cognitive_castle.knowledge_graph import KnowledgeGraph
        from cognitive_castle import mcp_server
        from cognitive_castle.embedding import embed_texts

        cfg_dir = str(tmp_path / "cfg")
        os.makedirs(cfg_dir)
        import json
        with open(os.path.join(cfg_dir, "config.json"), "w") as f:
            json.dump({"palace_path": palace}, f)

        cfg = MempalaceConfig(config_dir=cfg_dir)
        kg  = KnowledgeGraph(db_path=str(tmp_path / "kg.sqlite3"))

        monkeypatch.setattr(mcp_server, "_config", cfg)
        monkeypatch.setattr(mcp_server, "_kg", kg)
        monkeypatch.setenv("CASTLE_PROJECT", "test-project")
        # _vector_disabled removed — LanceDB has no HNSW divergence mode

        from cognitive_castle.backends.lancedb_backend import LanceDBBackend
        import cognitive_castle.palace as _palace
        backend = LanceDBBackend()
        monkeypatch.setattr(_palace, "_DEFAULT_BACKEND", backend)
        col = backend.get_collection(palace, collection_name="castle_drawers", create=True)

        docs = ["JWT tokens expire after 24 hours. Refresh via /auth/refresh."]
        vecs = embed_texts(docs)
        col.upsert(
            documents=docs, ids=["jwt-note"],
            metadatas=[{"wing": "project", "room": "backend", "source_file": "auth.md", "chunk_index": 0, "added_by": "test", "filed_at": "2026-01-01T00:00:00", "decay_score": 1.0}],
            embeddings=vecs,
        )

        # Simulate SOAR import failure
        import cognitive_castle.soar_bridge as _sb
        original = _sb._load_sml
        _sb._load_sml = lambda: (_ for _ in ()).throw(ImportError("no SOAR in this test"))

        try:
            result = mcp_server.tool_search(query="JWT token refresh")
            # Search must succeed even when SOAR is unavailable.
            assert "results" in result
            assert len(result["results"]) > 0
            # apply_soar_boosts swallows the error and returns un-boosted memories
            # so all soar_boost values should default to ×1.0.
            for hit in result["results"]:
                assert hit.get("soar_boost", 1.0) == pytest.approx(1.0)
        finally:
            _sb._load_sml = original
            kg.close()
            # _client_cache removed — LanceDB backend has no separate client cache
            mcp_server._collection_cache = None
