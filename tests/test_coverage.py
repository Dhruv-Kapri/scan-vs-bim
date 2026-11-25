"""Known answers for scan_vs_bim.coverage.face_coverage (#30's measure, kept for 03c)."""

import numpy as np

from scan_vs_bim.coverage import face_coverage

SQUARE_V: np.ndarray = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], float)
SQUARE_F: np.ndarray = np.array([[0, 1, 2], [0, 2, 3]])


def grid_points(x_hi: float, y_hi: float) -> np.ndarray:
    # one point at the centre of every 0.1 cell over [0, x_hi] x [0, y_hi], at z = 0
    gx, gy = np.meshgrid(np.arange(0.05, x_hi, 0.1), np.arange(0.05, y_hi, 0.1), indexing="ij")
    return np.column_stack([gx.ravel(), gy.ravel(), np.zeros(gx.size)])


def test_points_filling_the_face_cover_all_of_it() -> None:
    assert face_coverage(grid_points(1, 1), SQUARE_V, SQUARE_F, 2, 0.1) == 1.0


def test_points_over_half_the_cells_cover_half() -> None:
    assert face_coverage(grid_points(0.5, 1), SQUARE_V, SQUARE_F, 2, 0.1) == 0.5


def test_points_outside_the_face_are_ignored() -> None:
    pts = np.vstack([grid_points(0.5, 1), [[2.0, 2.0, 0.0], [-1.0, 0.5, 0.0]]])
    assert face_coverage(pts, SQUARE_V, SQUARE_F, 2, 0.1) == 0.5


def test_no_points_or_no_faces_gives_zero() -> None:
    assert face_coverage(np.zeros((0, 3)), SQUARE_V, SQUARE_F, 2, 0.1) == 0.0
    assert face_coverage(grid_points(1, 1), SQUARE_V, np.zeros((0, 3), int), 2, 0.1) == 0.0


def test_a_triangle_edge_on_in_the_projection_covers_nothing() -> None:
    # the square seen along y is a line: no face cells, so 0.0 whatever the points
    assert face_coverage(grid_points(1, 1), SQUARE_V, SQUARE_F, 1, 0.1) == 0.0
