"""
test_mcp_server.py — Tests for the MCP server tool handlers and dispatch.

Tests each tool handler directly (unit-level) and the handle_request
dispatch layer (integration-level). Uses isolated palace + KG fixtures
via monkeypatch to avoid touching real data.
"""

from datetime import datetime
import json

import pytest


def _patch_mcp_server(monkeypatch, config, kg):
    """Patch the mcp_server module globals to use test fixtures."""
    from cognitive_castle import mcp_server

    monkeypatch.setattr(mcp_server, "_config", config)
    monkeypatch.setattr(mcp_server, "_kg", kg)
    # Reset cached collection so it's re-opened against the patched config.
    monkeypatch.setattr(mcp_server, "_collection_cache", None)
    monkeypatch.setattr(mcp_server, "_metadata_cache", None)
    monkeypatch.setattr(mcp_server, "_metadata_cache_time", 0)


def _get_collection(palace_path, create=False):
    """Helper to get a LanceDB collection from the test palace.

    Returns (None, collection) — the None is a compat shim so callers
    that do ``_client, _col = _get_collection(...)`` continue to compile.
    """
    from cognitive_castle.palace import get_collection

    col = get_collection(palace_path, collection_name="castle_drawers", create=create)
    return None, col


# ── Protocol Layer ──────────────────────────────────────────────────────


class TestHandleRequest:
    def test_initialize(self):
        from cognitive_castle.mcp_server import handle_request

        resp = handle_request({"method": "initialize", "id": 1, "params": {}})
        assert resp["result"]["serverInfo"]["name"] == "cognitive-castle"
        assert resp["id"] == 1

    def test_initialize_negotiates_client_version(self):
        from cognitive_castle.mcp_server import handle_request

        resp = handle_request(
            {
                "method": "initialize",
                "id": 1,
                "params": {"protocolVersion": "2025-11-25"},
            }
        )
        assert resp["result"]["protocolVersion"] == "2025-11-25"

    def test_initialize_negotiates_older_supported_version(self):
        from cognitive_castle.mcp_server import handle_request

        resp = handle_request(
            {
                "method": "initialize",
                "id": 1,
                "params": {"protocolVersion": "2025-03-26"},
            }
        )
        assert resp["result"]["protocolVersion"] == "2025-03-26"

    def test_initialize_unknown_version_falls_back_to_latest(self):
        from cognitive_castle.mcp_server import handle_request

        resp = handle_request(
            {
                "method": "initialize",
                "id": 1,
                "params": {"protocolVersion": "9999-12-31"},
            }
        )
        from cognitive_castle.mcp_server import SUPPORTED_PROTOCOL_VERSIONS

        assert resp["result"]["protocolVersion"] == SUPPORTED_PROTOCOL_VERSIONS[0]

    def test_initialize_missing_version_uses_oldest(self):
        from cognitive_castle.mcp_server import handle_request, SUPPORTED_PROTOCOL_VERSIONS

        resp = handle_request({"method": "initialize", "id": 1, "params": {}})
        assert resp["result"]["protocolVersion"] == SUPPORTED_PROTOCOL_VERSIONS[-1]

    def test_notifications_initialized_returns_none(self):
        from cognitive_castle.mcp_server import handle_request

        resp = handle_request({"method": "notifications/initialized", "id": None, "params": {}})
        assert resp is None

    def test_ping_returns_empty_result(self):
        from cognitive_castle.mcp_server import handle_request

        resp = handle_request({"method": "ping", "id": 11, "params": {}})
        assert resp["id"] == 11
        assert resp["result"] == {}

    def test_tools_list(self):
        from cognitive_castle.mcp_server import handle_request

        resp = handle_request({"method": "tools/list", "id": 2, "params": {}})
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        assert "castle_status" in names
        assert "castle_search" in names
        assert "castle_add_drawer" in names
        assert "castle_kg_add" in names

    def test_null_arguments_does_not_hang(self, monkeypatch, config, palace_path, seeded_kg):
        """Sending arguments: null should return a result, not hang (#394)."""
        _patch_mcp_server(monkeypatch, config, seeded_kg)
        from cognitive_castle.mcp_server import handle_request

        _client, _col = _get_collection(palace_path, create=True)
        del _client
        resp = handle_request(
            {
                "method": "tools/call",
                "id": 10,
                "params": {"name": "castle_status", "arguments": None},
            }
        )
        assert "error" not in resp
        assert resp["result"] is not None

    def test_unknown_tool(self):
        from cognitive_castle.mcp_server import handle_request

        resp = handle_request(
            {
                "method": "tools/call",
                "id": 3,
                "params": {"name": "nonexistent_tool", "arguments": {}},
            }
        )
        assert resp["error"]["code"] == -32601

    def test_unknown_method(self):
        from cognitive_castle.mcp_server import handle_request

        resp = handle_request({"method": "unknown/method", "id": 4, "params": {}})
        assert resp["error"]["code"] == -32601

    def test_any_notification_returns_none(self):
        """All notifications/* methods should return None (no response)."""
        from cognitive_castle.mcp_server import handle_request

        for method in [
            "notifications/initialized",
            "notifications/cancelled",
            "notifications/progress",
            "notifications/roots/list_changed",
        ]:
            resp = handle_request({"method": method, "params": {}})
            assert resp is None, f"{method} should return None"

    def test_unknown_method_no_id_returns_none(self):
        """Messages without id (notifications) must never get a response."""
        from cognitive_castle.mcp_server import handle_request

        resp = handle_request({"method": "unknown/thing", "params": {}})
        assert resp is None

    def test_malformed_method_none(self):
        """method=None or missing should not crash."""
        from cognitive_castle.mcp_server import handle_request

        # Explicit None
        resp = handle_request({"method": None, "params": {}})
        assert resp is None  # no id → no response

        # Missing method entirely
        resp = handle_request({"params": {}})
        assert resp is None

        # method=None with id → should return error, not crash
        resp = handle_request({"method": None, "id": 99, "params": {}})
        assert resp["error"]["code"] == -32601

    def test_tools_call_dispatches(self, monkeypatch, config, palace_path, seeded_kg):
        _patch_mcp_server(monkeypatch, config, seeded_kg)
        from cognitive_castle.mcp_server import handle_request

        # Create a collection so status works
        _client, _col = _get_collection(palace_path, create=True)
        del _client

        resp = handle_request(
            {
                "method": "tools/call",
                "id": 5,
                "params": {"name": "castle_status", "arguments": {}},
            }
        )
        assert "result" in resp
        content = json.loads(resp["result"]["content"][0]["text"])
        assert "total_drawers" in content


# ── Read Tools ──────────────────────────────────────────────────────────


class TestReadTools:
    def test_status_cold_start_no_collection(self, monkeypatch, config, palace_path, kg):
        """Status on a valid palace directory with no drawers yet (#830).

        After `mempalace init`, the palace directory exists but no mine has run.
        Status should return total_drawers: 0, not 'No palace found'.
        """
        _patch_mcp_server(monkeypatch, config, kg)
        # palace_path already exists as a directory (from the fixture) — no
        # further setup needed. LanceDB creates the table on first access.
        from cognitive_castle.mcp_server import tool_status

        result = tool_status()
        assert "error" not in result, f"cold-start should not error: {result}"
        assert result["total_drawers"] == 0

    def test_status_empty_palace(self, monkeypatch, config, palace_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        _client, _col = _get_collection(palace_path, create=True)
        del _client
        from cognitive_castle.mcp_server import tool_status

        result = tool_status()
        assert result["total_drawers"] == 0
        assert result["wings"] == {}

    def test_status_with_data(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_status

        result = tool_status()
        assert result["total_drawers"] == 4
        assert "project" in result["wings"]
        assert "notes" in result["wings"]

    def test_status_handles_none_metadata_without_partial(
        self, monkeypatch, config, palace_path, kg
    ):
        """tool_status must not crash or go partial when the metadata cache
        returns a ``None`` entry — palaces can contain drawers with no
        metadata (older mining paths, third-party writes). Before the guard,
        ``m.get("wing")`` raised AttributeError mid-tally and the result
        carried ``"error"`` + ``"partial": True`` even though the data was
        perfectly fetchable."""
        from unittest.mock import patch as _patch

        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_status

        # Inject a metadata cache where one entry is None
        with _patch("cognitive_castle.mcp_server._get_collection") as mock_get_col:
            fake_col = type("C", (), {"count": lambda self: 2})()
            mock_get_col.return_value = fake_col
            with _patch(
                "cognitive_castle.mcp_server._get_cached_metadata",
                return_value=[{"wing": "proj", "room": "r"}, None],
            ):
                result = tool_status()

        # The None-metadata drawer falls under 'unknown/unknown' — no crash,
        # no partial flag.
        assert "error" not in result
        assert result.get("partial") is not True
        assert result["total_drawers"] == 2
        assert result["wings"].get("proj") == 1
        assert result["wings"].get("unknown") == 1

    def test_list_wings(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_list_wings

        result = tool_list_wings()
        assert result["wings"]["project"] == 3
        assert result["wings"]["notes"] == 1

    def test_list_rooms_all(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_list_rooms

        result = tool_list_rooms()
        assert "backend" in result["rooms"]
        assert "frontend" in result["rooms"]
        assert "planning" in result["rooms"]

    def test_list_rooms_filtered(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_list_rooms

        result = tool_list_rooms(wing="project")
        assert "backend" in result["rooms"]
        assert "planning" not in result["rooms"]

    def test_get_taxonomy(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_get_taxonomy

        result = tool_get_taxonomy()
        assert result["taxonomy"]["project"]["backend"] == 2
        assert result["taxonomy"]["project"]["frontend"] == 1
        assert result["taxonomy"]["notes"]["planning"] == 1

    def test_no_palace_returns_error(self, monkeypatch, config, kg, tmp_dir):
        """Status should return error when the palace directory doesn't exist."""
        import os as _os
        from cognitive_castle.config import CognitiveCastleConfig
        import json

        # Point config at a palace path that does not exist.
        nonexistent_palace = _os.path.join(tmp_dir, "does_not_exist")
        cfg_dir = _os.path.join(tmp_dir, "cfg_nopalace")
        _os.makedirs(cfg_dir)
        with open(_os.path.join(cfg_dir, "config.json"), "w") as f:
            json.dump({"palace_path": nonexistent_palace}, f)
        no_palace_config = CognitiveCastleConfig(config_dir=cfg_dir)

        from cognitive_castle import mcp_server as _mcp

        monkeypatch.setattr(_mcp, "_config", no_palace_config)
        monkeypatch.setattr(_mcp, "_kg", kg)
        monkeypatch.setattr(_mcp, "_collection_cache", None)
        monkeypatch.setattr(_mcp, "_metadata_cache", None)
        monkeypatch.setattr(_mcp, "_metadata_cache_time", 0)

        result = _mcp.tool_status()
        assert "error" in result


# ── Search Tool ─────────────────────────────────────────────────────────


class TestSearchTool:
    def test_search_basic(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_search

        result = tool_search(query="JWT authentication tokens")
        assert "results" in result
        assert len(result["results"]) > 0
        # Top result should be the auth drawer
        top = result["results"][0]
        assert "JWT" in top["text"] or "authentication" in top["text"].lower()

    def test_search_with_wing_filter(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_search

        result = tool_search(query="planning", wing="notes")
        assert all(r["wing"] == "notes" for r in result["results"])

    def test_search_with_room_filter(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_search

        result = tool_search(query="database", room="backend")
        assert all(r["room"] == "backend" for r in result["results"])

    def test_search_min_similarity_backwards_compat(
        self, monkeypatch, config, palace_path, seeded_collection, kg
    ):
        """Old min_similarity param still works via backwards-compat shim."""
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_search

        # Old name should work
        result = tool_search(query="JWT", min_similarity=1.5)
        assert "results" in result

        # Old name takes precedence when both provided
        result_strict = tool_search(query="JWT", max_distance=999.0, min_similarity=0.01)
        result_loose = tool_search(query="JWT", max_distance=0.01, min_similarity=999.0)
        assert len(result_strict["results"]) <= len(result_loose["results"])

    def test_list_rooms_rejects_invalid_wing(self, monkeypatch, config, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle import mcp_server

        monkeypatch.setattr(mcp_server, "_get_collection", lambda: pytest.fail())

        result = mcp_server.tool_list_rooms(wing="../etc/passwd")
        assert "error" in result

    def test_search_rejects_invalid_room(self, monkeypatch, config, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle import mcp_server

        monkeypatch.setattr(mcp_server, "search_memories", lambda: pytest.fail())

        result = mcp_server.tool_search(query="JWT", room="../backend")
        assert "error" in result

    def test_list_drawers_rejects_invalid_wing(self, monkeypatch, config, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle import mcp_server

        monkeypatch.setattr(mcp_server, "_get_collection", lambda: pytest.fail())

        result = mcp_server.tool_list_drawers(wing="../notes")
        assert "error" in result

    def test_find_tunnels_rejects_invalid_wing(self, monkeypatch, config, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle import mcp_server

        monkeypatch.setattr(mcp_server, "_get_collection", lambda: pytest.fail())

        result = mcp_server.tool_find_tunnels(wing_a="../project")
        assert "error" in result

    def test_wal_redacts_sensitive_fields(self, monkeypatch, config, kg, tmp_path):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle import mcp_server

        wal_file = tmp_path / "write_log.jsonl"
        monkeypatch.setattr(mcp_server, "_WAL_FILE", wal_file)

        mcp_server._wal_log(
            "test",
            {"content": "secret note", "query": "private search", "safe": "ok"},
        )

        entry = json.loads(wal_file.read_text().strip())
        assert entry["params"]["content"].startswith("[REDACTED")
        assert entry["params"]["query"].startswith("[REDACTED")
        assert entry["params"]["safe"] == "ok"


# ── Write Tools ─────────────────────────────────────────────────────────


class TestWriteTools:
    def test_add_drawer(self, monkeypatch, config, palace_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        _client, _col = _get_collection(palace_path, create=True)
        del _client
        from cognitive_castle.mcp_server import tool_add_drawer

        result = tool_add_drawer(
            wing="test_wing",
            room="test_room",
            content="This is a test memory about Python decorators and metaclasses.",
        )
        assert result["success"] is True
        assert result["wing"] == "test_wing"
        assert result["room"] == "test_room"
        assert result["drawer_id"].startswith("drawer_test_wing_test_room_")

    def test_add_drawer_duplicate_detection(self, monkeypatch, config, palace_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        _client, _col = _get_collection(palace_path, create=True)
        del _client
        from cognitive_castle.mcp_server import tool_add_drawer

        content = "This is a unique test memory about Rust ownership and borrowing."
        result1 = tool_add_drawer(wing="w", room="r", content=content)
        assert result1["success"] is True

        result2 = tool_add_drawer(wing="w", room="r", content=content)
        assert result2["success"] is True
        assert result2["reason"] == "already_exists"

    def test_add_drawer_shared_header_no_collision(self, monkeypatch, config, palace_path, kg):
        """Documents sharing a >100-char header must get distinct IDs (full-content hash)."""
        _patch_mcp_server(monkeypatch, config, kg)
        _client, _col = _get_collection(palace_path, create=True)
        del _client
        from cognitive_castle.mcp_server import tool_add_drawer

        header = "# ACME Corp Knowledge Base\n**Project:** Alpha | **Team:** Backend | **Status:** Active\n\n"
        doc1 = (
            header
            + "Decision: Use PostgreSQL for primary storage. Rationale: ACID compliance required."
        )
        doc2 = header + "Decision: Use Redis for session caching. Rationale: sub-ms latency needed."

        result1 = tool_add_drawer(wing="work", room="decisions", content=doc1)
        result2 = tool_add_drawer(wing="work", room="decisions", content=doc2)

        assert result1["success"] is True
        assert result2["success"] is True
        assert result1["drawer_id"] != result2["drawer_id"], (
            "Documents with shared header but different content must have distinct drawer IDs"
        )

    def test_delete_drawer(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_delete_drawer

        result = tool_delete_drawer("drawer_proj_backend_aaa")
        assert result["success"] is True
        assert seeded_collection.count() == 3

    def test_delete_drawer_not_found(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_delete_drawer

        result = tool_delete_drawer("nonexistent_drawer")
        assert result["success"] is False

    def test_check_duplicate(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_check_duplicate

        # Exact match text from seeded_collection should be flagged
        result = tool_check_duplicate(
            "The authentication module uses JWT tokens for session management. "
            "Tokens expire after 24 hours. Refresh tokens are stored in HttpOnly cookies.",
            threshold=0.5,
        )
        assert result["is_duplicate"] is True

        # Unrelated content should not be flagged
        result = tool_check_duplicate(
            "Black holes emit Hawking radiation at the event horizon.",
            threshold=0.99,
        )
        assert result["is_duplicate"] is False

    def test_get_drawer(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_get_drawer

        result = tool_get_drawer("drawer_proj_backend_aaa")
        assert result["drawer_id"] == "drawer_proj_backend_aaa"
        assert result["wing"] == "project"
        assert result["room"] == "backend"
        assert "JWT tokens" in result["content"]

    def test_get_drawer_not_found(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_get_drawer

        result = tool_get_drawer("nonexistent_drawer")
        assert "error" in result

    def test_get_drawer_does_not_leak_absolute_source_file_path(
        self, monkeypatch, config, palace_path, collection, kg
    ):
        """tool_get_drawer must not expose the absolute filesystem path
        that the miners write into ``source_file``. Same threat class as
        the palace_path leak in castle_status: in nested-agent or
        multi-server MCP topologies the client is a separate trust
        domain, and the directory layout of the host has no documented
        client-side use. Basename is enough for citation."""
        _patch_mcp_server(monkeypatch, config, kg)

        secret_dir = "/private/home/alice/secret-research/2026"
        absolute_source = f"{secret_dir}/notes.md"
        collection.add(
            ids=["drawer_leak_probe"],
            documents=["verbatim drawer body for leak probe"],
            metadatas=[
                {
                    "wing": "research",
                    "room": "notes",
                    "source_file": absolute_source,
                    "chunk_index": 0,
                    "added_by": "miner",
                    "filed_at": "2026-05-03T00:00:00",
                }
            ],
        )

        from cognitive_castle.mcp_server import tool_get_drawer

        result = tool_get_drawer("drawer_leak_probe")
        assert result["drawer_id"] == "drawer_leak_probe"
        assert result["metadata"]["source_file"] == "notes.md"
        # Defense-in-depth: no field anywhere in the response should
        # contain the absolute path or its parent directory.
        serialized = json.dumps(result)
        assert absolute_source not in serialized
        assert secret_dir not in serialized

    def test_list_drawers(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_list_drawers

        result = tool_list_drawers()
        assert result["count"] == 4
        assert len(result["drawers"]) == 4

    def test_list_drawers_with_wing_filter(
        self, monkeypatch, config, palace_path, seeded_collection, kg
    ):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_list_drawers

        result = tool_list_drawers(wing="project")
        assert result["count"] == 3
        assert all(d["wing"] == "project" for d in result["drawers"])

    def test_list_drawers_with_room_filter(
        self, monkeypatch, config, palace_path, seeded_collection, kg
    ):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_list_drawers

        result = tool_list_drawers(wing="project", room="backend")
        assert result["count"] == 2
        assert all(d["room"] == "backend" for d in result["drawers"])

    def test_list_drawers_pagination(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_list_drawers

        result = tool_list_drawers(limit=2, offset=0)
        assert result["count"] == 2
        assert result["limit"] == 2
        assert result["offset"] == 0

    def test_list_drawers_negative_offset_clamped(
        self, monkeypatch, config, palace_path, seeded_collection, kg
    ):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_list_drawers

        result = tool_list_drawers(offset=-5)
        assert result["offset"] == 0

    def test_update_drawer_content(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_update_drawer, tool_get_drawer

        result = tool_update_drawer(
            "drawer_proj_backend_aaa", content="Updated content about auth."
        )
        assert result["success"] is True

        fetched = tool_get_drawer("drawer_proj_backend_aaa")
        assert fetched["content"] == "Updated content about auth."

    def test_update_drawer_wing_and_room(
        self, monkeypatch, config, palace_path, seeded_collection, kg
    ):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_update_drawer

        result = tool_update_drawer("drawer_proj_backend_aaa", wing="new_wing", room="new_room")
        assert result["success"] is True
        assert result["wing"] == "new_wing"
        assert result["room"] == "new_room"

    def test_update_drawer_not_found(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_update_drawer

        result = tool_update_drawer("nonexistent_drawer", content="hello")
        assert result["success"] is False

    def test_update_drawer_noop(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_update_drawer

        result = tool_update_drawer("drawer_proj_backend_aaa")
        assert result["success"] is True
        assert result.get("noop") is True


# ── KG Tools ────────────────────────────────────────────────────────────


class TestKGTools:
    def test_kg_add(self, monkeypatch, config, palace_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_kg_add

        result = tool_kg_add(
            subject="Alice",
            predicate="likes",
            object="coffee",
            valid_from="2025-01-01",
        )
        assert result["success"] is True

    def test_kg_query(self, monkeypatch, config, palace_path, seeded_kg):
        _patch_mcp_server(monkeypatch, config, seeded_kg)
        from cognitive_castle.mcp_server import tool_kg_query

        result = tool_kg_query(entity="Max")
        assert result["count"] > 0

    def test_kg_invalidate(self, monkeypatch, config, palace_path, seeded_kg):
        _patch_mcp_server(monkeypatch, config, seeded_kg)
        from cognitive_castle.mcp_server import tool_kg_invalidate

        result = tool_kg_invalidate(
            subject="Max",
            predicate="does",
            object="chess",
            ended="2026-03-01",
        )
        assert result["success"] is True
        # Regression #1314: response must echo the actual ended date,
        # not silently drop it and return the literal string "today".
        assert result["ended"] == "2026-03-01"

    def test_kg_add_forwards_valid_to(self, monkeypatch, config, palace_path, kg):
        """Regression #1314 case 1: valid_to must round-trip through kg_add."""
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_kg_add

        result = tool_kg_add(
            subject="_test_temporal",
            predicate="had_value",
            object="probe",
            valid_from="2026-01-01",
            valid_to="2026-04-28",
        )
        assert result["success"] is True

        facts = kg.query_entity("_test_temporal")
        assert len(facts) == 1
        assert facts[0]["valid_from"] == "2026-01-01"
        assert facts[0]["valid_to"] == "2026-04-28"
        # An already-ended fact must not be reported as still current.
        assert facts[0]["current"] is False

    def test_kg_add_forwards_source_provenance(self, monkeypatch, config, palace_path, kg):
        """Regression #1314 case 3: source_file / source_drawer_id reach storage."""
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle.mcp_server import tool_kg_add

        result = tool_kg_add(
            subject="operating-verb",
            predicate="candidate",
            object="husbandry",
            valid_from="2026-04-28",
            source_closet="closet-42",
            source_file="docs/decisions.md",
            source_drawer_id="drawer_abc123",
        )
        assert result["success"] is True

        triple_id = result["triple_id"]
        # Read raw row to verify all provenance columns persisted.
        with kg._lock:
            row = (
                kg._conn()
                .execute(
                    "SELECT source_closet, source_file, source_drawer_id FROM triples WHERE id = ?",
                    (triple_id,),
                )
                .fetchone()
            )
        assert row is not None
        assert row["source_closet"] == "closet-42"
        assert row["source_file"] == "docs/decisions.md"
        assert row["source_drawer_id"] == "drawer_abc123"

    def test_kg_invalidate_returns_actual_ended_date(
        self, monkeypatch, config, palace_path, seeded_kg
    ):
        """Regression #1314 case 2: response reports the resolved date, not 'today'."""
        from datetime import date as _date

        _patch_mcp_server(monkeypatch, config, seeded_kg)
        from cognitive_castle.mcp_server import tool_kg_invalidate

        # Caller-supplied date round-trips into the response.
        explicit = tool_kg_invalidate(
            subject="Max",
            predicate="does",
            object="swimming",
            ended="2026-04-28",
        )
        assert explicit["ended"] == "2026-04-28"

        # Caller-omitted date resolves to today's ISO date — never the
        # literal string "today" the buggy implementation used to return.
        implicit = tool_kg_invalidate(
            subject="Max",
            predicate="loves",
            object="Chess",
        )
        assert implicit["ended"] != "today"
        assert implicit["ended"] == _date.today().isoformat()

    def test_kg_timeline(self, monkeypatch, config, palace_path, seeded_kg):
        _patch_mcp_server(monkeypatch, config, seeded_kg)
        from cognitive_castle.mcp_server import tool_kg_timeline

        result = tool_kg_timeline(entity="Alice")
        assert result["count"] > 0

    def test_kg_stats(self, monkeypatch, config, palace_path, seeded_kg):
        _patch_mcp_server(monkeypatch, config, seeded_kg)
        from cognitive_castle.mcp_server import tool_kg_stats

        result = tool_kg_stats()
        assert result["entities"] >= 4


# ── Diary Tools ─────────────────────────────────────────────────────────


class TestDiaryTools:
    def test_diary_write_and_read(self, monkeypatch, config, palace_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        _client, _col = _get_collection(palace_path, create=True)
        del _client
        from cognitive_castle.mcp_server import tool_diary_write, tool_diary_read

        w = tool_diary_write(
            agent_name="TestAgent",
            entry="Today we discussed authentication patterns.",
            topic="architecture",
        )
        assert w["success"] is True
        # agent_name is normalized to lowercase on write (#1243).
        assert w["agent"] == "testagent"

        r = tool_diary_read(agent_name="TestAgent")
        assert r["total"] == 1
        assert r["entries"][0]["topic"] == "architecture"
        assert "authentication" in r["entries"][0]["content"]

    def test_diary_read_empty(self, monkeypatch, config, palace_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        _client, _col = _get_collection(palace_path, create=True)
        del _client
        from cognitive_castle.mcp_server import tool_diary_read

        r = tool_diary_read(agent_name="Nobody")
        assert r["entries"] == []

    def test_diary_write_same_second_shared_prefix_no_collision(
        self, monkeypatch, config, palace_path, kg
    ):
        _patch_mcp_server(monkeypatch, config, kg)
        _client, _col = _get_collection(palace_path, create=True)
        del _client

        from cognitive_castle import mcp_server

        class FrozenDateTime:
            calls = [
                datetime(2026, 4, 13, 22, 15, 30, 123456),
                datetime(2026, 4, 13, 22, 15, 30, 123457),
            ]
            fallback = datetime(2026, 4, 13, 22, 15, 30, 123457)

            @classmethod
            def now(cls):
                if cls.calls:
                    return cls.calls.pop(0)
                return cls.fallback

        monkeypatch.setattr(mcp_server, "datetime", FrozenDateTime)

        from cognitive_castle.mcp_server import tool_diary_read, tool_diary_write

        entry1 = "A" * 50 + " entry one"
        entry2 = "A" * 50 + " entry two"

        result1 = tool_diary_write(agent_name="TestAgent", entry=entry1, topic="status")
        result2 = tool_diary_write(agent_name="TestAgent", entry=entry2, topic="status")

        assert result1["success"] is True
        assert result2["success"] is True
        assert result1["entry_id"] != result2["entry_id"]

        read_result = tool_diary_read(agent_name="TestAgent")
        contents = [entry["content"] for entry in read_result["entries"]]
        assert read_result["total"] == 2
        assert entry1 in contents
        assert entry2 in contents

    def test_diary_read_empty_wing_spans_all_wings(self, monkeypatch, config, palace_path, kg):
        """diary_read(wing='') must return entries from every wing this agent
        wrote to. Hooks write to project-derived wings (#659); a reader that
        silos by default wing would never see those entries."""
        _patch_mcp_server(monkeypatch, config, kg)
        _client, _col = _get_collection(palace_path, create=True)
        del _client
        from cognitive_castle.mcp_server import tool_diary_read, tool_diary_write

        w1 = tool_diary_write(
            agent_name="TestAgent",
            entry="default-wing entry",
            topic="general",
        )
        w2 = tool_diary_write(
            agent_name="TestAgent",
            entry="project-wing entry",
            topic="general",
            wing="wing_someproject",
        )
        assert w1["success"] and w2["success"]

        # Empty wing → return both entries
        r = tool_diary_read(agent_name="TestAgent", wing="")
        assert r["total"] == 2
        contents = {e["content"] for e in r["entries"]}
        assert "default-wing entry" in contents
        assert "project-wing entry" in contents

        # Explicit wing → return only that wing's entries
        r_scoped = tool_diary_read(agent_name="TestAgent", wing="wing_someproject")
        assert r_scoped["total"] == 1
        assert r_scoped["entries"][0]["content"] == "project-wing entry"

    def test_diary_read_case_insensitive_agent(self, monkeypatch, config, palace_path, kg):
        """Regression for #1243: diary_read must be case-insensitive over
        agent_name. Writing as "Claude" and reading as "claude" (or vice
        versa) must surface the same entries — sanitize_name preserved
        case, which silently dropped reads when the agent name's casing
        differed from the write."""
        _patch_mcp_server(monkeypatch, config, kg)
        _client, _col = _get_collection(palace_path, create=True)
        del _client
        from cognitive_castle.mcp_server import tool_diary_read, tool_diary_write

        # Write as "Claude" → read as "claude" should match.
        w1 = tool_diary_write(
            agent_name="Claude",
            entry="entry written as Claude",
            topic="general",
        )
        assert w1["success"]

        r1 = tool_diary_read(agent_name="claude")
        assert "entries" in r1, r1
        contents1 = {e["content"] for e in r1["entries"]}
        assert "entry written as Claude" in contents1

        # Write as "CLAUDE" → read as "Claude" should also match the
        # same agent. After normalization both writes target the same
        # lowercase agent identity, so both entries are returned.
        w2 = tool_diary_write(
            agent_name="CLAUDE",
            entry="entry written as CLAUDE",
            topic="general",
        )
        assert w2["success"]

        r2 = tool_diary_read(agent_name="Claude")
        contents2 = {e["content"] for e in r2["entries"]}
        assert "entry written as Claude" in contents2
        assert "entry written as CLAUDE" in contents2

        # The stored agent metadata is the lowercase form, and the
        # default wing is derived from that lowercase form too.
        assert w1["agent"] == "claude"
        assert w2["agent"] == "claude"


# ── Cache Invalidation (inode/mtime) ──────────────────────────────────


class TestCacheInvalidation:
    """Tests for _get_collection cache invalidation logic."""

    def test_reconnect_reports_failure_when_no_palace(self, monkeypatch, config, kg):
        """tool_reconnect should report failure when no collection is available."""
        _patch_mcp_server(monkeypatch, config, kg)
        from cognitive_castle import mcp_server

        # Make _get_collection always return None
        monkeypatch.setattr(mcp_server, "_get_collection", lambda create=False: None)

        result = mcp_server.tool_reconnect()
        assert result["success"] is False
        assert "No palace found" in result["message"]
        assert result["drawers"] == 0

    def test_reconnect_reports_success(self, monkeypatch, config, palace_path, kg):
        """tool_reconnect should report success with drawer count."""
        _patch_mcp_server(monkeypatch, config, kg)
        _client, _col = _get_collection(palace_path, create=True)
        del _client
        from cognitive_castle import mcp_server

        result = mcp_server.tool_reconnect()
        assert result["success"] is True
        assert "Reconnected" in result["message"]
        assert isinstance(result["drawers"], int)


def test_mcp_tool_search_default_mode_is_max():
    from unittest.mock import patch
    from cognitive_castle import mcp_server

    with patch(
        "cognitive_castle.mcp_server.search_memories",
        return_value={"results": []},
    ) as m:
        mcp_server.tool_search(query="q")
    assert m.call_args.kwargs.get("mode") == "max"


def test_mcp_tool_search_accepts_valid_modes():
    from unittest.mock import patch
    from cognitive_castle import mcp_server

    for mode in ("fast", "standard", "boosted", "max"):
        with patch(
            "cognitive_castle.mcp_server.search_memories",
            return_value={"results": []},
        ):
            result = mcp_server.tool_search(query="q", mode=mode)
        assert "error" not in result, f"mode={mode} returned error: {result}"


def test_mcp_tool_search_rejects_invalid_mode():
    from cognitive_castle import mcp_server

    result = mcp_server.tool_search(query="q", mode="full")
    assert "error" in result
    assert "invalid mode" in result["error"].lower()


def test_palace_protocol_has_no_circular_wakeup_rule():
    """PALACE_PROTOCOL is now injected at session start; it shouldn't
    instruct the AI to call castle_status (the protocol's source) on
    wake-up — that's the very thing the injection replaces."""
    from cognitive_castle.mcp_server import PALACE_PROTOCOL
    assert "ON WAKE-UP" not in PALACE_PROTOCOL
    assert "Call castle_status" not in PALACE_PROTOCOL


def test_aaak_spec_uses_generic_placeholders():
    """The AAAK spec ships with example entity codes that get injected
    into every user's system prompt. Personal-name examples (Alice,
    Jordan, etc.) are replaced with neutral placeholders. Emotion
    mappings (*warm*=joy, *fierce*=determined) stay — those define the
    AAAK dialect itself, not user data."""
    from cognitive_castle.mcp_server import AAAK_SPEC
    # Personal names removed
    for personal in ("Alice", "Jordan", "Riley", "Max=Max", "BEN=Ben"):
        assert personal not in AAAK_SPEC, (
            f"AAAK_SPEC still contains personal-name example: {personal!r}"
        )
    # Placeholders present
    assert "ENT1" in AAAK_SPEC
    assert "PersonAlpha" in AAAK_SPEC
    # Emotion mappings preserved (these ARE the dialect, not data)
    assert "*warm*=joy" in AAAK_SPEC


def test_palace_state_line_returns_none_on_failure(monkeypatch):
    """Initialize must never fail because of a palace state read.
    A broken palace path or LanceDB error returns None; injection
    proceeds without the dynamic line."""
    from cognitive_castle import mcp_server

    def _raise(*args, **kwargs):
        raise RuntimeError("lance broken")

    monkeypatch.setattr(mcp_server.os.path, "isdir", lambda p: True)
    monkeypatch.setattr(mcp_server, "_get_collection", _raise)
    assert mcp_server._palace_state_line() is None


def test_palace_state_line_with_drawers(monkeypatch):
    """The N-drawers-across-M-wings code path is not exercised on a
    fresh CI machine (no `castle init` run). Mock the collection +
    metadata so this code path is covered."""
    from cognitive_castle import mcp_server

    class FakeCol:
        def count(self):
            return 42

    fake_meta = [
        {"wing": "wing_castle"},
        {"wing": "wing_castle"},
        {"wing": "wing_alice"},
        {"wing": None},
    ]

    monkeypatch.setattr(mcp_server.os.path, "isdir", lambda p: True)
    monkeypatch.setattr(mcp_server, "_get_collection", lambda **kw: FakeCol())
    monkeypatch.setattr(mcp_server, "_get_cached_metadata", lambda col: fake_meta)

    line = mcp_server._palace_state_line()
    assert "42 drawers" in line
    # 3 distinct wings: wing_castle, wing_alice, "unknown" (None → fallback)
    assert "3 wings" in line
