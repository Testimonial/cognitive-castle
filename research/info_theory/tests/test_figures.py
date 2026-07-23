from analysis.figures import emit_tables_from_results


def test_emit_tables_writes_one_tex_per_table(tmp_path):
    results = {
        "K_sensitivity": {"K=10": {"alpha": 0.5}, "K=20": {"alpha": 0.48}},
        "per_stratum_fits": {"miner::room1": {"alpha": 0.6, "tau": None}},
    }
    out_dir = tmp_path / "appendix"
    emit_tables_from_results(results, out_dir)
    assert (out_dir / "table_K_sensitivity.tex").exists()
    assert (out_dir / "table_per_stratum_fits.tex").exists()
    content = (out_dir / "table_K_sensitivity.tex").read_text()
    assert "\\begin{tabular}" in content


def test_emit_tables_skips_empty_groups(tmp_path):
    results = {"empty_group": {}}
    out_dir = tmp_path / "appendix"
    emit_tables_from_results(results, out_dir)
    assert not (out_dir / "table_empty_group.tex").exists()
