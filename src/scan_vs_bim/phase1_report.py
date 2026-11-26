"""The summary of the Phase 1 benchmark's CSV (issue #39): docs/phase-1-results.md, filled into `phase1_results.md.tmpl`."""

from collections import Counter
from collections.abc import Mapping, Sequence
from importlib import resources
from pathlib import Path
from string import Template

import numpy as np

from scan_vs_bim.pc2model import BUILDING_CATEGORIES
from scan_vs_bim.register import CENTROID_MAX_M, ROT_MAX_DEG, SCALE_MAX_REL

# Gate agreement: judgement calls for "agree" (registration is seeded, so near-exact is expected).
AGREE_ROT_DEG: float = 0.01
AGREE_CENTROID_M: float = 0.001
AGREE_SCALE_PCT: float = 0.01

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
    v = [float(r[key]) for r in rows if r[key] != "nan"]   # nan: a model with no triangles, failed and not measured
    if not v:
        return "-"
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


def _summary_table(rows: Sequence[Mapping[str, str]]) -> str:
    table = ["| group | scale | n | success, all (k/n) | success, unseen only (k/n) | seed 0 success (context) | rot_deg median / p90 | centroid_m median / p90 | scale_err_pct median / p90 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for label, cats in _LINES:
        table += _line(label, [r for r in rows if r["category"] in cats])
    building = [r for r in rows if r["category"] in BUILDING_CATEGORIES]
    table += _line("building (37)", building) + _line("objects (100)", [r for r in rows if r["category"] not in BUILDING_CATEGORIES])
    return "\n".join(table + _line("all", list(rows)))


def _gate_table(agree: Sequence[Mapping[str, object]]) -> str:
    table = ["| sample | benchmark success | 05a success | d rot_deg | d centroid_m | d scale_err_pct | agrees |", "|---|---|---|---|---|---|---|"]
    for a in agree:
        if a["missing"]:
            table.append(f"| {a['sample']} | missing | - | - | - | - | no |")
        else:
            table.append(f"| {a['sample']} | {a['bench_success']} | {a['gate_success']} | {a['d_rot_deg']:.3g} | {a['d_centroid_m']:.3g} | "
                         f"{a['d_scale_pct']:.3g} | {'yes' if a['agrees'] else 'no'} |")
    return "\n".join(table)


def _ngon_table(rows: Sequence[Mapping[str, str]], non_triangle: Mapping[str, float], before: Sequence[Mapping[str, str]] | None) -> str:
    success = {r["sample"]: r["success"] for r in rows}
    by_name = {r["sample"]: r for r in rows}
    old_by_name = {r["sample"]: r for r in before or []}

    def metric(r: Mapping[str, str] | None, key: str) -> str:
        return "-" if r is None or r[key] == "nan" else f"{float(r[key]):.4g}"

    if before is None:
        table = ["| sample | non-triangle faces | success |", "|---|---|---|"]
    else:
        table = ["| sample | non-triangle faces | success before | success now | rot_deg before | rot_deg now | centroid_m before | centroid_m now |",
                 "|---|---|---|---|---|---|---|---|"]
    for name, share in sorted(non_triangle.items(), key=lambda kv: kv[1]):
        if share <= 0:
            continue
        now, was = by_name.get(name), old_by_name.get(name)
        if before is None:
            table.append(f"| {name} | {100 * share:.1f}% | {success.get(name, 'not scored')} |")
        else:
            table.append(f"| {name} | {100 * share:.1f}% | {was['success'] if was else 'not scored'} | {success.get(name, 'not scored')} | "
                         f"{metric(was, 'rot_deg')} | {metric(now, 'rot_deg')} | {metric(was, 'centroid_m')} | {metric(now, 'centroid_m')} |")
    return "\n".join(table)


ROOM_B_HEADING: str = "## Room B after Phase 1"  # #47: a hand-written section at the end of docs/phase-1-results.md, kept by `with_kept_section`


def with_kept_section(generated: str, old: str | None) -> str:
    """`generated` (the tables of `results_markdown`) followed by the hand-written section of the old doc, from `ROOM_B_HEADING` to its end, if it has one."""
    at = -1 if old is None else old.find("\n" + ROOM_B_HEADING + "\n")
    return generated if old is None or at < 0 else generated.rstrip("\n") + "\n" + old[at:]


def results_markdown(
    rows: Sequence[Mapping[str, str]], gate_rows: Sequence[Mapping[str, str]], command: str, *,
    expected: Sequence[str], non_triangle: Mapping[str, float], before: Sequence[Mapping[str, str]] | None = None,
) -> str:
    """The body of docs/phase-1-results.md from the benchmark CSV rows and 05a's registration.csv rows (all values text).
    `expected`: every sample's zip folder (those without a row are listed as not scored); `non_triangle`: share of non-triangle
    faces by sample name, for the models that have any (`obj_mesh.non_triangle_share`); `before`: the benchmark rows from before #53, when
    given the table of those models shows success, rot_deg and centroid_m before and now. The prose is in `phase1_results.md.tmpl`."""
    per_commit = Counter(r["commit"] for r in rows)  # rows re-run on a later commit keep that commit (the CSV's commit column, per row)
    heaviest = max(rows, key=lambda r: float(r["peak_rss_gb"]), default=None)
    agree = gate_agreement(rows, gate_rows)
    scored = {r["folder"] for r in rows}
    template = Template(resources.files("scan_vs_bim").joinpath("phase1_results.md.tmpl").read_text(encoding="utf-8"))
    return template.substitute(
        command=command,
        commits=", ".join(f"{c} ({n})" for c, n in sorted(per_commit.items(), key=lambda kv: (-kv[1], kv[0]))) or "-",
        n_rows=len(rows), n_expected=len(expected),
        cost="-" if heaviest is None else (
            f"{sum(float(r['run_s']) for r in rows) / 3600:.1f} h summed over the samples' run_s; largest per-sample peak RSS "
            f"{float(heaviest['peak_rss_gb']):.2f} GB ({heaviest['sample']})"),
        rot_max=ROT_MAX_DEG, centroid_max=CENTROID_MAX_M, scale_max=SCALE_MAX_REL,
        summary=_summary_table(rows),
        agree_rot=AGREE_ROT_DEG, agree_centroid=AGREE_CENTROID_M, agree_scale=AGREE_SCALE_PCT,
        gate_table=_gate_table(agree), all_agree="yes" if agree and all(a["agrees"] for a in agree) else "no",
        unscored="\n".join([f"- {Path(f).name}" for f in expected if f not in scored] or ["none"]),
        ngons=_ngon_table(rows, non_triangle, before),
    )
