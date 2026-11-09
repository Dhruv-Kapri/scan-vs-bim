import numpy as np
import pytest

from scan_vs_bim.ramp import block_resamples, plane_gradient

RNG = np.random.default_rng(0)


def test_a_known_plane_with_different_offset_per_group_is_recovered() -> None:
    x, y = RNG.uniform(-10, 10, 60), RNG.uniform(0, 20, 60)
    groups = np.where(x < 0, 2.30, 2.64)  # two ceiling levels; one shared slope
    values = groups + 0.0012 * x - 0.0008 * y
    g = plane_gradient(x, y, values, groups)
    assert (g.gx, g.gy) == pytest.approx((0.0012, -0.0008))
    assert g.intercepts == pytest.approx({2.30: 2.30, 2.64: 2.64})  # the value at x = y = 0
    assert g.rms == pytest.approx(0, abs=1e-12)


def test_without_groups_there_is_one_intercept_and_the_rms_is_what_the_plane_leaves() -> None:
    x, y = np.array([0.0, 1, 0, 1]), np.array([0.0, 0, 1, 1])
    values = 0.5 + 0.1 * x + 0.2 * y + np.array([0.01, -0.01, -0.01, 0.01])  # a plane plus a twist no plane can follow
    g = plane_gradient(x, y, values)
    assert (g.gx, g.gy) == pytest.approx((0.1, 0.2))
    assert list(g.intercepts.values()) == pytest.approx([0.5])
    assert g.rms == pytest.approx(0.01)


def test_a_group_of_one_cell_adds_no_slope_information_and_does_not_disturb_the_slope() -> None:
    x, y = np.array([0.0, 2, 0, 2, 5]), np.array([0.0, 0, 2, 2, 5])
    groups = np.array([1, 1, 1, 1, 2])
    values = np.where(groups == 1, 0.0, 9.0) + 0.003 * x - 0.001 * y
    g = plane_gradient(x, y, values, groups)
    assert (g.gx, g.gy) == pytest.approx((0.003, -0.001))
    assert g.intercepts[2] == pytest.approx(9.0)


def test_positions_on_one_line_have_no_gradient_across_it_and_are_refused() -> None:
    x = np.arange(6.0)
    with pytest.raises(ValueError, match="line"):
        plane_gradient(x, 2 * x + 1, 0.01 * x)
    with pytest.raises(ValueError, match="line"):  # two groups, each with one position repeated: nothing left once the offsets are removed
        plane_gradient(np.array([0.0, 0, 1, 1]), np.array([0.0, 0, 1, 1]), np.zeros(4), np.array([1, 1, 2, 2]))


def test_block_resamples_keep_whole_squares_and_are_seeded() -> None:
    x, y = np.array([0.5, 1.5, 6.0, 6.5, 12.0]), np.array([0.5, 1.0, 6.0, 7.0, 1.0])  # squares of 4 m: {0, 1}, {2, 3}, {4}
    runs = [[r.tolist() for r in block_resamples(x, y, 4.0, 20, seed)] for seed in (1, 1, 2)]
    assert runs[0] == runs[1] != runs[2]
    for r in runs[0]:
        counts = {i: r.count(i) for i in set(r)}
        assert counts.get(0, 0) == counts.get(1, 0) and counts.get(2, 0) == counts.get(3, 0)  # a square comes with all its cells
