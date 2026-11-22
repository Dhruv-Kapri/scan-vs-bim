"""Write docs/phase-1-results.md from the benchmark CSV and 05a's registration.csv (issue #39); prints whether the gate rows agree."""

import argparse
from pathlib import Path

from scan_vs_bim.benchmark import gate_agreement, results_markdown
from scan_vs_bim.tables import read_rows

REPO = Path(__file__).resolve().parent.parent
COMMAND: str = "uv run python scripts/run_benchmark.py"   # the run's exact command


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", type=Path, default=REPO / "outputs" / "phase1" / "registration.csv")
    ap.add_argument("--gate-csv", type=Path, default=REPO / "outputs" / "05a" / "registration.csv")
    ap.add_argument("--out", type=Path, default=REPO / "docs" / "phase-1-results.md")
    args = ap.parse_args(argv)
    rows, gate_rows = read_rows(args.csv), read_rows(args.gate_csv)
    args.out.write_text(results_markdown(rows, gate_rows, COMMAND))
    agree = gate_agreement(rows, gate_rows)
    print(f"wrote {args.out}; gate rows agreeing: {sum(bool(a['agrees']) for a in agree)}/{len(agree)}")


if __name__ == "__main__":
    main()
