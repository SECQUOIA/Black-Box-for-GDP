"""Published Grid TTS99 values, extended-real medians and figure-only updates."""
import json
import math
import random
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
from matplotlib.markers import MarkerStyle
import numpy as np
import pytest

from scripts import analyze_grid_gdp_paths as analysis


SOURCE = analysis.OUTPUT / "tts99_summary.csv"
SOURCE_SHA256 = "fd0bb1a3bb3dc356ad2bf695b2633e98b756939822a48808e5e8803b5e55e07c"
EXPECTED_INFINITY = [(17, 4, 4, 4, 4), (7, 2, 0, 0, 0),
                     (9, 7, 4, 3, 2), (15, 6, 2, 1, 0)]


def test_published_matrix_and_medians_include_infinity():
    assert analysis.sha(SOURCE.read_bytes()) == SOURCE_SHA256
    groups = analysis.load_tts99_groups(SOURCE)
    assert len(groups) == 20
    assert [g["infinite"] for g in groups] == [n for row in EXPECTED_INFINITY for n in row]
    assert sum(len(g["values"]) for g in groups) == 420
    assert sum(math.isfinite(v) for g in groups for v in g["values"]) == 329
    assert [(g["method"], g["budget"]) for g in groups if math.isinf(g["median"])] == [
        ("dsda", 10), ("fmqa_sa", 10)]
    for group in groups:
        assert len(set(group["grids"])) == 21
        assert group["median"] == sorted(group["values"])[10]
    bam10 = groups[10]
    assert bam10["median"] != statistics.median(v for v in bam10["values"] if math.isfinite(v))


@pytest.mark.parametrize("corruption", ["duplicate", "missing", "unknown_method", "wrong_budget",
                                        "nan", "-inf", "0", "-1", "infinity_count"])
def test_invalid_matrix_or_values_are_rejected(tmp_path, corruption):
    rows = analysis.read_table(SOURCE)
    if corruption == "duplicate":
        rows[0] = rows[1].copy()
    elif corruption == "missing":
        rows.pop()
    elif corruption == "unknown_method":
        rows[0]["method"] = "unknown"
    elif corruption == "wrong_budget":
        rows[0]["max_evals"] = 11
    elif corruption == "infinity_count":
        row = next(row for row in rows if math.isinf(float(row["tts99_s"])))
        row["tts99_s"] = "1"
    else:
        rows[0]["tts99_s"] = corruption
    path = tmp_path / "summary.csv"
    analysis.write_table(path, rows)
    with pytest.raises(ValueError):
        analysis.load_tts99_groups(path)


def test_scatter_values_markers_medians_and_label_clearance(tmp_path):
    groups = analysis.load_tts99_groups(SOURCE)
    fig = analysis.plot_tts99(groups)
    try:
        assert len(fig.axes) == 1
        ax = fig.axes[0]
        assert ax.get_yscale() == "log"
        assert ax.get_ylabel() == "Estimated TTS99 (s, log scale)"
        assert not ax.get_title() and fig._suptitle is None
        artists = {a.get_gid(): a for a in [*ax.collections, *ax.texts]}
        assert len(ax.texts) == 26  # 20 infinity counts, two infinite medians, four method labels
        assert len(ax.collections) == 38  # 20 scatter columns and 18 finite median lines
        for index, group in enumerate(groups):
            method, budget = group["method"], group["budget"]
            suffix = f"{method}-{budget}"
            x = 6 * (index // 5) + index % 5
            points = artists[f"tts99-points-{suffix}"]
            offsets = points.get_offsets()
            np.testing.assert_array_equal(offsets[:, 1], [v for v in group["values"] if math.isfinite(v)])
            assert all(abs(offsets[:, 0] - x) <= .210001)
            np.testing.assert_allclose(points.get_facecolors()[0], to_rgba(analysis.COLORS[method], .78))
            marker = MarkerStyle(["o", "s", "D", "^", "P"][index % 5])
            np.testing.assert_array_equal(points.get_paths()[0].vertices,
                                          marker.get_path().transformed(marker.get_transform()).vertices)
            assert artists[f"tts99-infinity-{suffix}"].get_text() == f"∞×{group['infinite']}"
            if math.isfinite(group["median"]):
                line = artists[f"tts99-median-{suffix}"]
                np.testing.assert_allclose(line.get_segments()[0],
                                           [[x - .31, group["median"]], [x + .31, group["median"]]])
                np.testing.assert_array_equal(line.get_colors()[0], to_rgba("black"))
            else:
                assert artists[f"tts99-infinite-median-{suffix}"].get_text() == "median = ∞"
        assert [t.get_text() for t in ax.get_xticklabels()] == ["10", "30", "50", "70", "100"] * 4
        assert [artists[f"tts99-method-{m}"].get_text() for m in analysis.METHODS] == [
            "DSDA", "RBFOpt", "BAM", "FMQA-SA"]
        assert [t.get_text() for t in fig.legends[0].get_texts()] == [
            "B=10", "B=30", "B=50", "B=70", "B=100", "Median"]
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        labels = [*ax.texts, *ax.get_xticklabels(), ax.yaxis.label, fig.legends[0]]
        boxes = [label.get_window_extent(renderer) for label in labels]
        for box in boxes:
            assert fig.bbox.contains(box.x0, box.y0) and fig.bbox.contains(box.x1, box.y1)
        for i, box in enumerate(boxes):
            assert not any(box.overlaps(other) for other in boxes[i + 1:])
        assert all(t.get_window_extent(renderer).y1 < ax.bbox.y0 - 5 for t in ax.get_xticklabels())

        rows = analysis.read_table(SOURCE)
        random.Random(42).shuffle(rows)
        shuffled = tmp_path / "shuffled.csv"
        analysis.write_table(shuffled, rows)
        other = analysis.plot_tts99(analysis.load_tts99_groups(shuffled))
        try:
            for original, reordered in zip(ax.collections, other.axes[0].collections):
                np.testing.assert_array_equal(original.get_offsets(), reordered.get_offsets())
        finally:
            plt.close(other)
    finally:
        plt.close(fig)


def test_figure_only_cli_preserves_data_other_figures_and_aliases(tmp_path, monkeypatch):
    output = tmp_path / "results/current"
    legacy = tmp_path / "results/fmqa_20260925/analysis/grid"
    output.mkdir(parents=True)
    legacy.mkdir(parents=True)
    source = SOURCE.read_bytes()
    contents = {"tts99_summary.csv": source, "runs.csv": b"unchanged scientific data\n",
                "tts99.pdf": b"old PDF", "tts99.png": b"old PNG",
                "performance_profiles.png": b"unchanged other figure"}
    for name, content in contents.items():
        (output / name).write_bytes(content)
    manifest = {"analysis_sha256": "historical analysis",
                "artifacts_sha256": {name: analysis.sha(data) for name, data in contents.items()}}
    (output / "manifest.json").write_text(json.dumps(manifest))
    (legacy / "tts99_summary.csv").write_bytes(source)
    (legacy / "evaluation_performance_profiles.png").write_bytes(b"unchanged alias")
    old_aliases = {"unrelated": {"source": "untouched", "sha256": "unchanged"}}
    (legacy / "grid_gdp_figures.manifest.json").write_text(json.dumps({"aliases": old_aliases}))
    monkeypatch.setattr(analysis, "ROOT", tmp_path)
    monkeypatch.setattr(analysis, "RESULTS", tmp_path / "results")

    def forbidden(*args, **kwargs):
        pytest.fail("Figure-only CLI must not load trajectories or recalculate scientific data")

    for name in ("reference_data", "tts_summary", "plot_figures", "load_archive", "gdp_runs"):
        monkeypatch.setattr(analysis, name, forbidden)
    analysis.main(["--tts99-only", "--output", str(output), "--update-published",
                   "--bam-archive", str(tmp_path / "absent.zip")])
    updated = json.loads((output / "manifest.json").read_text())
    assert updated["analysis_sha256"] == manifest["analysis_sha256"]
    assert updated["tts99_figure"]["source_sha256"] == SOURCE_SHA256
    assert updated["tts99_figure"]["observations"] == 420
    for name, content in contents.items():
        if name not in ("tts99.png", "tts99.pdf"):
            assert (output / name).read_bytes() == content
        assert analysis.sha((output / name).read_bytes()) == updated["artifacts_sha256"][name]
    assert (legacy / "tts99_summary.csv").read_bytes() == source
    assert (legacy / "evaluation_performance_profiles.png").read_bytes() == b"unchanged alias"
    for ext in ("png", "pdf"):
        assert (legacy / f"tts99_comparison.{ext}").read_bytes() == (output / f"tts99.{ext}").read_bytes()
    for name in ("grid_gdp_figures.manifest.json", "tts99_manifest.json"):
        pointer = json.loads((legacy / name).read_text())
        assert pointer["analysis_manifest_sha256"] == analysis.sha((output / "manifest.json").read_bytes())
    pointer = json.loads((legacy / "grid_gdp_figures.manifest.json").read_text())
    assert pointer["aliases"]["unrelated"] == old_aliases["unrelated"]
