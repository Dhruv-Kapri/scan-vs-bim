"""Write docs/phase-1-results.md from the benchmark CSV and 05a's registration.csv (issue #39); prints whether the gate rows agree.
Keeps the doc's hand-written "Room B after Phase 1" section (#47) at its end.
Also reads outputs/pc2model_scales.csv (the samples expected) and every model OBJ in data/pc2model (its non-triangle faces)."""

import argparse
from pathlib import Path

from scan_vs_bim.benchmark import gate_agreement, non_triangle_share, results_markdown, with_kept_section
from scan_vs_bim.pc2model import download_order
from scan_vs_bim.tables import read_rows

REPO = Path(__file__).resolve().parent.parent
COMMAND: str = "uv run python scripts/run_benchmark.py"   # the run's exact command


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", type=Path, default=REPO / "outputs" / "phase1" / "registration.csv")
    ap.add_argument("--gate-csv", type=Path, default=REPO / "outputs" / "05a" / "registration.csv")
    ap.add_argument("--scales", type=Path, default=REPO / "outputs" / "pc2model_scales.csv")
    ap.add_argument("--data", type=Path, default=REPO / "data" / "pc2model")
    ap.add_argument("--before", type=Path, default=REPO / "outputs" / "phase1" / "registration_before_53.csv",
                    help="benchmark rows from before #53 (used if the file exists)")
    ap.add_argument("--out", type=Path, default=REPO / "docs" / "phase-1-results.md")
    args = ap.parse_args(argv)
    rows, gate_rows = read_rows(args.csv), read_rows(args.gate_csv)
    expected = download_order(read_rows(args.scales))
    non_triangle = {Path(f).name: non_triangle_share(next((args.data / Path(f).name).glob("model_*.obj"))) for f in expected}
    generated = results_markdown(rows, gate_rows, COMMAND, expected=expected, non_triangle=non_triangle, before=read_rows(args.before) if args.before.exists() else None)
    args.out.write_text(with_kept_section(generated, args.out.read_text() if args.out.exists() else None))  # the hand-written room-B section (#47) survives a re-run
    agree = gate_agreement(rows, gate_rows)
    print(f"wrote {args.out}; gate rows agreeing: {sum(bool(a['agrees']) for a in agree)}/{len(agree)}")


if __name__ == "__main__":
    main()
