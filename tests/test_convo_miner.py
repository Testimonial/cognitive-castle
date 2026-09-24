import os
import tempfile
import shutil
from pathlib import Path

from cognitive_castle.backends.lancedb_backend import LanceDBBackend
from cognitive_castle.convo_miner import mine_convos
from cognitive_castle.palace import file_already_mined, get_collection


def test_convo_mining():
    tmpdir = tempfile.mkdtemp()
    with open(os.path.join(tmpdir, "chat.txt"), "w") as f:
        f.write(
            "> What is memory?\nMemory is persistence.\n\n> Why does it matter?\nIt enables continuity.\n\n> How do we build it?\nWith structured storage.\n"
        )

    palace_path = os.path.join(tmpdir, "palace")
    mine_convos(tmpdir, palace_path, wing="test_convos")

    col = LanceDBBackend().get_collection(palace_path, "castle_drawers")
    assert col.count() >= 2

    # Verify search works
    results = col.query(query_texts=["memory persistence"], n_results=1)
    assert len(results["documents"][0]) > 0

    shutil.rmtree(tmpdir, ignore_errors=True)


def test_mine_convos_does_not_reprocess_short_files(capsys):
    """Short files are stored verbatim and skipped only while unchanged."""
    tmpdir = tempfile.mkdtemp()
    try:
        # A file too short to produce any chunks
        with open(os.path.join(tmpdir, "tiny.txt"), "w") as f:
            f.write("hi")

        palace_path = os.path.join(tmpdir, "palace")

        # First run -- file is processed (sentinel written)
        mine_convos(tmpdir, palace_path, wing="test")
        capsys.readouterr()  # drain output

        # Verify the short text was filed (resolve path -- macOS /var -> /private/var)
        resolved_file = str(Path(tmpdir).resolve() / "tiny.txt")
        col = get_collection(palace_path)
        assert file_already_mined(col, resolved_file)

        # Second run -- file should be skipped
        mine_convos(tmpdir, palace_path, wing="test")
        out2 = capsys.readouterr().out
        assert "Files skipped (already filed): 1" in out2
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_mine_convos_does_not_reprocess_empty_chunk_files(capsys):
    """Files that normalize but produce 0 exchange chunks get a sentinel."""
    tmpdir = tempfile.mkdtemp()
    try:
        # Content long enough to pass MIN_CHUNK_SIZE but with no exchange markers
        # (no "> " lines), so chunk_exchanges returns []
        with open(os.path.join(tmpdir, "no_exchanges.txt"), "w") as f:
            f.write("This is a plain paragraph without any exchange markers. " * 5)

        palace_path = os.path.join(tmpdir, "palace")

        mine_convos(tmpdir, palace_path, wing="test")
        mine_convos(tmpdir, palace_path, wing="test")
        out2 = capsys.readouterr().out
        assert "Files skipped (already filed): 1" in out2
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_schema_upgrade_preserves_previous_revision(tmp_path, monkeypatch):
    from cognitive_castle import palace, convo_miner

    source = tmp_path / "source"
    source.mkdir()
    path = source / "chat.txt"
    path.write_text("> Original words.\nOriginal answer.\n")
    palace_path = str(tmp_path / "palace")
    with monkeypatch.context() as old_version:
        old_version.setattr(palace, "NORMALIZE_VERSION", 2)
        old_version.setattr(convo_miner, "NORMALIZE_VERSION", 2)
        mine_convos(str(source), palace_path, wing="test")
    col = get_collection(palace_path)
    old = col.get(where={"source_file": str(path)})
    assert old.ids
    assert not file_already_mined(col, str(path), check_mtime=True)
    mine_convos(str(source), palace_path, wing="test")
    assert col.get(ids=old.ids).documents == old.documents
    current = col.get(where={"source_file": str(path)})
    assert set(old.ids) < set(current.ids)
    assert file_already_mined(col, str(path), check_mtime=True)


# ---------------------------------------------------------------------------
# KG enrichment hook tests
# ---------------------------------------------------------------------------


def test_mine_convos_invokes_enrich_palace(tmp_path, monkeypatch):
    """mine_convos() calls kg_enricher.enrich_palace after the main loop."""
    called = {"n": 0}

    def stub_enrich(palace_path, cfg):
        called["n"] += 1
        return {
            "drawers_scanned": 0,
            "entities_promoted": 0,
            "triples_written": 0,
            "elapsed_s": 0.01,
        }

    monkeypatch.setattr("cognitive_castle.kg_enricher.enrich_palace", stub_enrich)

    convos = tmp_path / "convos"
    convos.mkdir()
    palace = tmp_path / "palace"

    mine_convos(str(convos), str(palace))

    assert called["n"] == 1


def test_mine_convos_continues_when_enrich_palace_raises(tmp_path, monkeypatch, capsys):
    """A failure inside enrich_palace must not break mine_convos() — caller warns
    and continues."""

    def stub_enrich(palace_path, cfg):
        raise RuntimeError("simulated enrich failure")

    monkeypatch.setattr("cognitive_castle.kg_enricher.enrich_palace", stub_enrich)

    convos = tmp_path / "convos"
    convos.mkdir()
    palace = tmp_path / "palace"

    # Should NOT raise
    mine_convos(str(convos), str(palace))

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "KG enrichment FAILED" in output
