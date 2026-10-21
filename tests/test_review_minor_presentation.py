"""Check added displayed paired evidence and readable Dynamic cost axes."""

import pytest

from review_comparison import manuscript as m


@pytest.fixture(scope="module")
def groups():
    return m.load()[1]


def test_selected_process_pairs_and_direction(groups):
    dynamic = m.process_pair(groups, "dynamic", 12, m.GEN, "dsda")
    assert [dynamic[k] for k in ("both_success", "new_only_success", "reference_only_success", "neither_success")] == [4, 6, 0, 0]
    assert dynamic["difference"] == pytest.approx(0.6)
    reverse = m.process_pair(groups, "dynamic", 12, "dsda", m.GEN)
    assert reverse["difference"] == -dynamic["difference"]
    assert reverse["low"] == pytest.approx(-dynamic["high"])
    batch = m.process_pair(groups, "small_batch", 10, "fmqa_sa", m.UNI)
    assert [batch[k] for k in ("both_success", "new_only_success", "reference_only_success", "neither_success")] == [2, 4, 2, 2]
    assert batch["difference"] == pytest.approx(0.2)
    assert batch["low"] < 0 < batch["high"]


@pytest.mark.parametrize("replacement", ["missing", "duplicate"])
def test_selected_process_pairs_reject_invalid_seed_sets(groups, replacement):
    changed = dict(groups)
    key = ("process", "dynamic", 12, m.GEN)
    records = list(groups[key])
    changed[key] = records[:-1] if replacement == "missing" else records[:-1] + [records[0]]
    with pytest.raises(ValueError, match="paired seeds"):
        m.process_pair(changed, "dynamic", 12, m.GEN, "dsda")


@pytest.mark.parametrize("axis", ["x", "y"])
@pytest.mark.parametrize("limits", [(12, 55), (14, 56)])
def test_narrow_log_axes_have_numeric_ticks_without_changing_limits(axis, limits):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    fig, ax = plt.subplots()
    if axis == "x":
        ax.set(xscale="log", xlim=limits)
    else:
        ax.set(yscale="log", ylim=limits)
    m.label_dynamic_cost_axis(ax, axis)
    fig.canvas.draw()
    target = ax.xaxis if axis == "x" else ax.yaxis
    labels = [label.get_text() for label in target.get_ticklabels()]
    assert len(labels) >= 3 and all(float(label) > 0 for label in labels)
    assert (ax.get_xlim() if axis == "x" else ax.get_ylim()) == limits
    plt.close(fig)
