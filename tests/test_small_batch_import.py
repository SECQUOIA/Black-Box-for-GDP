"""Recheck published raw evidence independently of the exported plotting CSVs."""

import pytest

from scripts.import_small_batch_full_domain import ROOT, audit, verify_archive


def test_dantzig_archive_reconciles_with_point_sources_and_aggregate_tables(tmp_path):
    path = ROOT / "results/archives/small_batch_full_domain_20261012_024647_d4390oed.zip"
    count = verify_archive(path, tmp_path)
    result = audit(tmp_path, count)
    assert result["archived_files_verified"] == 355
    assert result["executed_source_files_verified"] == 85
    assert result["callback_counts"] == dict.fromkeys(("dsda", "rbfopt", "bam", "fmqa_sa"), 100)
    assert [m["target_hits"] for m in result["methods"]] == [8, 5, 2, 7]
    assert sum(m["infeasible_evaluations"] for m in result["methods"]) == 197
    # A changed exported cost must be rejected even if raw traces remain intact.
    costs = tmp_path / "evaluation_costs.csv"
    costs.write_text(costs.read_text().replace("0.044", "0.144", 1))
    with pytest.raises(ValueError, match="Aggregate CSV differs"):
        audit(tmp_path, count)
