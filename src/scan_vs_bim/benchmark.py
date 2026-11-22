"""The Phase 1 registration benchmark (issue #39): 05a's registration (`register.register_sample`, ADR 0001) on every PC2Model sample,
one CSV row per sample, resumable, each sample in its own process; and the summary of the CSV (docs/phase-1-results.md)."""

import concurrent.futures
import csv
import logging
import multiprocessing
import time
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path

import numpy as np
import open3d as o3d

from scan_vs_bim.load import load_e57
from scan_vs_bim.memory import peak_rss_gb
from scan_vs_bim.pc2model import BUILDING_CATEGORIES, parse_transform, scale_of
from scan_vs_bim.register import CENTROID_MAX_M, ROT_MAX_DEG, SCALE_MAX_REL, register_sample, score, seed_all

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

# Gate agreement: judgement calls for "agree" (registration is seeded, so near-exact is expected).
AGREE_ROT_DEG: float = 0.01
AGREE_CENTROID_M: float = 0.001
AGREE_SCALE_PCT: float = 0.01


def seen_mark(folder: str, gate: Collection[str], tuning: Collection[str]) -> str:
    """"gate" (a Phase 0.5 gate sample), "tuning" (05c's) or "unseen"; gate wins if both."""
    return "gate" if folder in gate else "tuning" if folder in tuning else "unseen"


def score_sample(folder: str, data_dir: Path, seen: str, commit: str) -> dict[str, object]:
    """Load (as 05a's load_sample does, same call order), register and score one sample; the row, keyed by COLUMNS."""
    t0 = time.perf_counter()
    d = data_dir / Path(folder).name
    try:
        obj, txt, e57 = (next(d.glob(g)) for g in ("model_*.obj", "transformation_matrix_*.txt", "pointcloud_*_transformed.e57"))
    except StopIteration:
        raise FileNotFoundError(f"{d} lacks model/transform/scan files: run scripts/fetch_all_samples.py") from None
    mesh = o3d.io.read_triangle_mesh(obj)
    T_gt = parse_transform(txt.read_text())
    seed_all(SEED)
    model = mesh.sample_points_uniformly(MODEL_POINTS)
    scan = load_e57(e57, MAX_SCAN_POINTS, SEED, CHUNK_POINTS)
    diag = float(np.linalg.norm(mesh.get_axis_aligned_bounding_box().get_extent()))
    load_s = time.perf_counter() - t0

    pts = np.asarray(scan.points)
    voxel = VOXEL_FRACTION * diag
    res = register_sample(scan, model, voxel)
    sc, sc0 = score(res.T, T_gt, pts), score(res.T_seed0, T_gt, pts)
    gt_scale = scale_of(T_gt)
    return dict(
        sample=Path(folder).name, folder=folder, category=folder.split("/")[1], seen=seen, scaled=abs(gt_scale - 1) > SCALED_TOL,
        gt_scale=gt_scale, est_scale=scale_of(res.T), rot_deg=sc.rot_deg, centroid_m=sc.centroid_m, scale_err_pct=100 * sc.scale_err,
        success=sc.success, best_seed=res.seed, seed0_rot_deg=sc0.rot_deg, seed0_centroid_m=sc0.centroid_m,
        seed0_scale_err_pct=100 * sc0.scale_err, seed0_success=sc0.success, n_scan_points=len(pts), voxel_m=voxel,
        load_s=load_s, coarse_s=res.coarse_s, refine_s=res.refine_s, run_s=time.perf_counter() - t0,
        peak_rss_gb=peak_rss_gb(), commit=commit)


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


# ---- the summary of the CSV ----------------------------------------------------------------------------------------------------

_LINES: list[tuple[str, tuple[str, ...]]] = [
    ("house", ("house",)),
    ("simulated indoor (indoor_modelling)", ("indoor_modelling",)),
    ("real indoor (ISPRS_indoor_modeling_benchmark)", ("ISPRS_indoor_modeling_benchmark",)),
    ("furniture", ("furniture",)),
    ("home_decor", ("home_decor",)),
    ("mechanical", ("mechanical",)),
    ("vehicle", ("vehicle",)),
]


def _is(v: str) -> bool:
    return v == "True"


def _rate(rows: Sequence[Mapping[str, str]], key: str = "success") -> str:
    return f"{sum(_is(r[key]) for r in rows)}/{len(rows)}"


def _stat(rows: Sequence[Mapping[str, str]], key: str) -> str:
    if not rows:
        return "-"
    v = [float(r[key]) for r in rows]
    return f"{np.percentile(v, 50):.4g} / {np.percentile(v, 90):.4g}"


def _line(label: str, rows: Sequence[Mapping[str, str]]) -> list[str]:
    out: list[str] = []
    for kind, sub in (("unscaled", [r for r in rows if not _is(r["scaled"])]), ("scaled", [r for r in rows if _is(r["scaled"])])):
        unseen = [r for r in sub if r["seen"] == "unseen"]
        if sub:
            pct = f"{100 * sum(_is(r['success']) for r in sub) / len(sub):.0f}%"
            cells = [str(len(sub)), f"{_rate(sub)} ({pct})", _rate(unseen), _rate(sub, "seed0_success"),
                     _stat(sub, "rot_deg"), _stat(sub, "centroid_m"), _stat(sub, "scale_err_pct")]
        else:
            cells = ["0"] + ["-"] * 6
        out.append("| " + " | ".join([label, kind] + cells) + " |")
    return out


def non_triangle_share(obj: Path) -> float:
    """Share of an OBJ's faces that are not triangles: Open3D's reader drops them silently, so the model is sampled without them
    (all of veh_008's faces are quads: no triangles left, and the load fails)."""
    n = other = 0
    with obj.open() as f:
        for line in f:
            if line.startswith("f "):
                n += 1
                other += len(line.split()) != 4
    return other / n if n else 0.0


def gate_agreement(rows: Sequence[Mapping[str, str]], gate_rows: Sequence[Mapping[str, str]]) -> list[dict[str, object]]:
    """Per 05a row (by `sample`): the benchmark row's success against 05a's, the absolute differences, and whether they agree.
    A sample with no benchmark row is `missing` and does not agree."""
    by_sample = {r["sample"]: r for r in rows}
    out: list[dict[str, object]] = []
    for g in gate_rows:
        b = by_sample.get(g["sample"])
        if b is None:
            out.append(dict(sample=g["sample"], missing=True, agrees=False))
            continue
        d_rot, d_cen, d_sc = (abs(float(b[k]) - float(g[k])) for k in ("rot_deg", "centroid_m", "scale_err_pct"))
        agrees = (_is(b["success"]) == _is(g["success"]) and d_rot <= AGREE_ROT_DEG and d_cen <= AGREE_CENTROID_M and d_sc <= AGREE_SCALE_PCT)
        out.append(dict(sample=g["sample"], missing=False, bench_success=_is(b["success"]), gate_success=_is(g["success"]),
                        d_rot_deg=d_rot, d_centroid_m=d_cen, d_scale_pct=d_sc, agrees=agrees))
    return out


def results_markdown(
    rows: Sequence[Mapping[str, str]], gate_rows: Sequence[Mapping[str, str]], command: str, *,
    expected: Sequence[str], non_triangle: Mapping[str, float],
) -> str:
    """The body of docs/phase-1-results.md from the benchmark CSV rows and 05a's registration.csv rows (all values text).
    `expected`: every sample's zip folder (those without a row are listed as not scored); `non_triangle`: share of non-triangle
    faces by sample name, for the models that have any (`non_triangle_share`)."""
    commits = ", ".join(sorted({r["commit"] for r in rows})) or "-"
    heaviest = max(rows, key=lambda r: float(r["peak_rss_gb"]), default=None)
    cost = "-" if heaviest is None else (
        f"{sum(float(r['run_s']) for r in rows) / 3600:.1f} h summed over the samples' run_s; largest per-sample peak RSS "
        f"{float(heaviest['peak_rss_gb']):.2f} GB ({heaviest['sample']})")
    head = ["| group | scale | n | success, all (k/n) | success, unseen only (k/n) | seed 0 success (context) | rot_deg median / p90 | centroid_m median / p90 | scale_err_pct median / p90 |",
            "|---|---|---|---|---|---|---|---|---|"]
    body: list[str] = []
    for label, cats in _LINES:
        body += _line(label, [r for r in rows if r["category"] in cats])
    building = [r for r in rows if r["category"] in BUILDING_CATEGORIES]
    body += _line("building (37)", building) + _line("objects (100)", [r for r in rows if r["category"] not in BUILDING_CATEGORIES])
    body += _line("all", list(rows))

    agree = gate_agreement(rows, gate_rows)
    glines = ["| sample | benchmark success | 05a success | d rot_deg | d centroid_m | d scale_err_pct | agrees |", "|---|---|---|---|---|---|---|"]
    for a in agree:
        if a["missing"]:
            glines.append(f"| {a['sample']} | missing | - | - | - | - | no |")
        else:
            glines.append(f"| {a['sample']} | {a['bench_success']} | {a['gate_success']} | {a['d_rot_deg']:.3g} | {a['d_centroid_m']:.3g} | "
                          f"{a['d_scale_pct']:.3g} | {'yes' if a['agrees'] else 'no'} |")
    all_agree = bool(agree) and all(a["agrees"] for a in agree)

    scored = {r["folder"] for r in rows}
    unscored = [f"- {Path(f).name}" for f in expected if f not in scored] or ["none"]
    success = {r["sample"]: r["success"] for r in rows}
    lost = ["| sample | faces dropped at load | success |", "|---|---|---|"]
    lost += [f"| {name} | {100 * share:.1f}% | {success.get(name, 'not scored')} |"
             for name, share in sorted(non_triangle.items(), key=lambda kv: kv[1]) if share > 0]
    return "\n".join([
        "# Phase 1 registration benchmark", "",
        f"Command: `{command}`", "", f"Commit(s): {commits}", "", f"Samples present: {len(rows)} of {len(expected)}", "", f"Cost: {cost}", "",
        "Generated from outputs/phase1/registration.csv by `uv run python scripts/write_phase1_results.py`.", "",
        f"Success: rotation error <= {ROT_MAX_DEG} deg, centroid error <= {CENTROID_MAX_M} m, relative scale error <= {SCALE_MAX_REL} "
        "(judgement calls, CONTEXT.md \"Registration success\"). Unseen = neither a Phase 0.5 gate sample nor one of 05c's tuning samples.", "",
        *head, *body, "",
        "## Agreement with the Phase 0.5 gate (05a)", "",
        f"A gate row agrees when its success equals 05a's and the differences are within {AGREE_ROT_DEG} deg, {AGREE_CENTROID_M} m and "
        f"{AGREE_SCALE_PCT} percentage points (judgement calls; registration is seeded, so near-exact is expected).", "",
        *glines, "", f"all agree: {'yes' if all_agree else 'no'}", "",
        "## Not scored", "", "Samples whose run raised (scripts/run_benchmark.py logs the error):", "", *unscored, "",
        "## Models with non-triangle faces", "",
        "Open3D's OBJ reader skips faces that are not triangles, without an error, so these models were sampled from their triangles "
        "only (05a's loader, kept frozen). The share counts faces, not area.", "", *lost, ""])
