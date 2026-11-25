"""The Phase 1 registration benchmark (issue #39): 05a's registration (`register.register_sample`, ADR 0001) on every PC2Model sample,
one CSV row per sample, resumable, each sample in its own process. The summary of the CSV (docs/phase-1-results.md) is `phase1_report`."""

import concurrent.futures
import csv
import logging
import multiprocessing
import time
from collections.abc import Collection, Sequence
from pathlib import Path

import numpy as np
import open3d as o3d

from scan_vs_bim.load import load_e57
from scan_vs_bim.memory import peak_rss_gb
from scan_vs_bim.obj_mesh import load_model_mesh
from scan_vs_bim.pc2model import parse_transform, scale_of
from scan_vs_bim.register import register_sample, score, seed_all

log = logging.getLogger(__name__)

# 05a's values (notebooks/05a_registration_gate.ipynb cell 2), unchanged, so the gate rows reproduce 05a's.
SEED: int = 0
MODEL_POINTS: int = 500_000
MAX_SCAN_POINTS: int = 1_000_000
CHUNK_POINTS: int = 1_000_000
VOXEL_FRACTION: float = 0.008
SCALED_TOL: float = 1e-3   # reporting only: the registration does not use it (ADR 0001)

# 05c's four real samples (notebooks/05c_registration_tuning.ipynb cell 2; its synthetic x0.8 copy is not a sample).
TUNING_SAMPLES: tuple[str, ...] = (
    "PC2Model_v1.4/furniture/fur_010-modelnet",
    "PC2Model_v1.4/house/house_6-sketchfab",
    "PC2Model_v1.4/indoor_modelling/indoor_modelling_5-ISPRS_indoor_modelling-GM",
    "PC2Model_v1.4/ISPRS_indoor_modeling_benchmark/real-indoor_modelling_5-ISPRS_indoor_modelling-GM",
)

COLUMNS: list[str] = [
    "sample", "folder", "category", "seen", "scaled", "gt_scale", "est_scale", "rot_deg", "centroid_m", "scale_err_pct", "success",
    "best_seed", "seed0_rot_deg", "seed0_centroid_m", "seed0_scale_err_pct", "seed0_success", "n_scan_points", "voxel_m",
    "load_s", "coarse_s", "refine_s", "run_s", "peak_rss_gb", "commit",
]

_NAN: float = float("nan")
# What a sample that was never registered has: NaN errors, no seed, no scan points, 0 s of coarse and refine; `_row` takes the rest from its caller.
_UNREGISTERED: dict[str, object] = dict(
    est_scale=_NAN, rot_deg=_NAN, centroid_m=_NAN, scale_err_pct=_NAN, success=False, best_seed=-1, seed0_rot_deg=_NAN, seed0_centroid_m=_NAN,
    seed0_scale_err_pct=_NAN, seed0_success=False, n_scan_points=0, voxel_m=_NAN, coarse_s=0.0, refine_s=0.0)


def _row(**values: object) -> dict[str, object]:
    """A row keyed by COLUMNS, in order: `values` over `_UNREGISTERED`; a column left unset by both, or a key that is not a column, raises."""
    row = {**_UNREGISTERED, **values}
    if row.keys() != set(COLUMNS):
        raise ValueError(f"row keys differ from COLUMNS: {sorted(row.keys() ^ set(COLUMNS))}")
    return {c: row[c] for c in COLUMNS}


def seen_mark(folder: str, gate: Collection[str], tuning: Collection[str]) -> str:
    """"gate" (a Phase 0.5 gate sample), "tuning" (05c's) or "unseen"; gate wins if both."""
    return "gate" if folder in gate else "tuning" if folder in tuning else "unseen"


def score_sample(folder: str, data_dir: Path, seen: str, commit: str) -> dict[str, object]:
    """Load (as 05a's load_sample does, same call order, via `load_model_mesh`), register and score one sample; the row, keyed by COLUMNS."""
    t0 = time.perf_counter()
    d = data_dir / Path(folder).name
    try:
        obj, txt, e57 = (next(d.glob(g)) for g in ("model_*.obj", "transformation_matrix_*.txt", "pointcloud_*_transformed.e57"))
    except StopIteration:
        raise FileNotFoundError(f"{d} lacks model/transform/scan files: run scripts/fetch_all_samples.py") from None
    mesh = load_model_mesh(obj)
    T_gt = parse_transform(txt.read_text())
    gt_scale = scale_of(T_gt)
    who = dict(sample=Path(folder).name, folder=folder, category=folder.split("/")[1], seen=seen, scaled=abs(gt_scale - 1) > SCALED_TOL,
               gt_scale=gt_scale, commit=commit)
    if not mesh.has_triangles():   # an OBJ with no faces at all: nothing to register
        t = time.perf_counter() - t0
        return _row(**who, load_s=t, run_s=t, peak_rss_gb=peak_rss_gb())
    seed_all(SEED)
    model = mesh.sample_points_uniformly(MODEL_POINTS)
    scan = load_e57(e57, MAX_SCAN_POINTS, SEED, CHUNK_POINTS)
    diag = float(np.linalg.norm(mesh.get_axis_aligned_bounding_box().get_extent()))
    load_s = time.perf_counter() - t0

    pts = np.asarray(scan.points)
    voxel = VOXEL_FRACTION * diag
    res = register_sample(scan, model, voxel)
    sc, sc0 = score(res.T, T_gt, pts), score(res.T_seed0, T_gt, pts)
    return _row(
        **who, est_scale=scale_of(res.T), rot_deg=sc.rot_deg, centroid_m=sc.centroid_m, scale_err_pct=100 * sc.scale_err, success=sc.success,
        best_seed=res.seed, seed0_rot_deg=sc0.rot_deg, seed0_centroid_m=sc0.centroid_m, seed0_scale_err_pct=100 * sc0.scale_err,
        seed0_success=sc0.success, n_scan_points=len(pts), voxel_m=voxel, load_s=load_s, coarse_s=res.coarse_s, refine_s=res.refine_s,
        run_s=time.perf_counter() - t0, peak_rss_gb=peak_rss_gb())


def _done_folders(out_csv: Path) -> set[str]:
    if not out_csv.exists():
        return set()
    with out_csv.open(newline="") as f:
        return {r["folder"] for r in csv.DictReader(f)}


def run_benchmark(
    folders: Sequence[str], data_dir: Path, out_csv: Path, gate: Collection[str], tuning: Collection[str], commit: str
) -> list[str]:
    """Score each folder not yet in out_csv, in order, each in a fresh child process (so peak_rss_gb is that sample's own), and append
    its row at once. A sample that raises or kills its child is logged and skipped; returns those folders."""
    done = _done_folders(out_csv)
    todo = [f for f in folders if f not in done]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    ctx = multiprocessing.get_context("spawn")
    for n, folder in enumerate(todo, 1):
        try:
            with concurrent.futures.ProcessPoolExecutor(max_workers=1, mp_context=ctx) as pool:
                row = pool.submit(score_sample, folder, data_dir, seen_mark(folder, gate, tuning), commit).result()
        except Exception as e:   # the child's own exception, or BrokenProcessPool if it died
            log.error("failed %d/%d: %s: %s: %s", n, len(todo), folder, type(e).__name__, e)
            failed.append(folder)
            continue
        with out_csv.open("a", newline="") as f:
            w = csv.DictWriter(f, COLUMNS)
            if f.tell() == 0:
                w.writeheader()
            w.writerow(row)
            f.flush()
        log.info("done %d/%d: %s success=%s run_s=%.0f peak_rss_gb=%.2f", n, len(todo), folder, row["success"], row["run_s"], row["peak_rss_gb"])
    return failed
