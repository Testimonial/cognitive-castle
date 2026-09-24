"""Recovery diagnostics must isolate bad records and require explicit deletion."""

from unittest.mock import MagicMock

import pytest

from cognitive_castle import repair


@pytest.fixture
def collection(monkeypatch):
    col = MagicMock()
    backend = MagicMock()
    backend.get_collection.return_value = col
    monkeypatch.setattr(repair, "LanceDBBackend", lambda: backend)
    return col


def test_scan_records_only_unreadable_ids(tmp_path, collection):
    collection.count.return_value = 4

    def get(*, ids=None, **kwargs):
        if ids is None:
            return {"ids": ["ok", "missing", "broken", "ok2"]}
        if len(ids) > 1 or ids == ["broken"]:
            raise RuntimeError("damaged fragment")
        return {"ids": [] if ids == ["missing"] else ids}

    collection.get.side_effect = get
    good, bad = repair.scan_palace(str(tmp_path), only_wing="project")
    assert good == {"ok", "ok2"}
    assert bad == {"missing", "broken"}
    assert (tmp_path / "corrupt_ids.txt").read_text().splitlines() == ["broken", "missing"]
    collection.delete.assert_not_called()
    assert collection.get.call_args_list[0].kwargs["where"] == {"wing": "project"}


def test_scan_detects_ids_missing_from_successful_batch(tmp_path, collection):
    collection.count.return_value = 2
    collection.get.side_effect = [{"ids": ["ok", "missing"]}, {"ids": ["ok"]}]
    assert repair.scan_palace(str(tmp_path)) == ({"ok"}, {"missing"})


def test_scan_empty_palace(tmp_path, collection):
    collection.count.return_value = 0
    collection.get.return_value = {"ids": []}
    assert repair.scan_palace(str(tmp_path)) == (set(), set())
    assert not (tmp_path / "corrupt_ids.txt").exists()


def test_prune_requires_scan_and_confirmation(tmp_path, collection):
    repair.prune_corrupt(str(tmp_path), confirm=True)
    collection.delete.assert_not_called()
    (tmp_path / "corrupt_ids.txt").write_text("bad\n")
    repair.prune_corrupt(str(tmp_path))
    collection.delete.assert_not_called()


def test_prune_falls_back_per_id_and_keeps_unlisted_records(tmp_path, collection, capsys):
    records = {"keep", "bad", "locked"}
    (tmp_path / "corrupt_ids.txt").write_text("bad\n\nlocked\n")
    collection.count.side_effect = lambda: len(records)

    def delete(*, ids):
        if len(ids) > 1 or ids == ["locked"]:
            raise RuntimeError("locked")
        records.difference_update(ids)

    collection.delete.side_effect = delete
    repair.prune_corrupt(str(tmp_path), confirm=True)
    assert records == {"keep", "locked"}
    out = capsys.readouterr().out
    assert "Deleted: 1" in out
    assert "Failed:  1" in out


def test_prune_successful_batch(tmp_path, collection):
    (tmp_path / "corrupt_ids.txt").write_text("bad\n")
    collection.count.side_effect = [2, 1]
    repair.prune_corrupt(str(tmp_path), confirm=True)
    collection.delete.assert_called_once_with(ids=["bad"])


def test_status_reports_storage_errors_without_deleting(tmp_path, collection, monkeypatch):
    collection.count.side_effect = [3, RuntimeError("unreadable closets")]
    report = repair.status(str(tmp_path))
    assert report["castle_drawers"] == {"count": 3, "status": "ok"}
    assert report["castle_closets"]["status"] == "error"
    collection.delete.assert_not_called()
    assert repair.status(str(tmp_path / "absent"))["status"] == "unknown"


def test_rebuild_unavailable_or_empty_storage_is_untouched(tmp_path, collection):
    repair.rebuild_index(str(tmp_path / "absent"))
    collection.count.side_effect = [RuntimeError("unreadable"), 0]
    repair.rebuild_index(str(tmp_path))
    repair.rebuild_index(str(tmp_path))
    collection.upsert.assert_not_called()
    collection.delete.assert_not_called()
