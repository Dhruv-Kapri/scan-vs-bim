"""Run the Phase 1 registration benchmark on every PC2Model sample (issue #39), one row per sample into outputs/phase1/registration.csv.

Samples come from outputs/pc2model_scales.csv in download order (building categories first), loaded from data/pc2model/<sample>/
(scripts/fetch_all_samples.py). Resumable: samples already in the CSV are skipped. Each sample runs in its own process. It runs for
hours, so run it detached (see the cras-cache pattern in CLAUDE.md). Exits non-zero if any sample failed.
"""

import argparse
import csv
import logging
import subprocess
from pathlib import Path

from scan_vs_bim.benchmark import TUNING_SAMPLES, run_benchmark
from scan_vs_bim.pc2model import download_order

REPO = Path(__file__).resolve().parent.parent


def _commit() -> str:
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
    return git("rev-parse", "--short", "HEAD") + ("-dirty" if git("status", "--porcelain", "--untracked-files=no") else "")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scales", type=Path, default=REPO / "outputs" / "pc2model_scales.csv")
    ap.add_argument("--gate", type=Path, default=REPO / "outputs" / "05a" / "gate_samples.csv")
    ap.add_argument("--data", type=Path, default=REPO / "data" / "pc2model")
    ap.add_argument("--out", type=Path, default=REPO / "outputs" / "phase1" / "registration.csv")
    ap.add_argument("--only", action="append", default=[], metavar="FOLDER", help="zip folder to run; repeatable; keeps download order")
    args = ap.parse_args(argv)
    if not args.scales.exists():
        raise SystemExit(f"{args.scales} not found: run `uv run python scripts/find_scaled_sample.py --no-fetch` first")
    if not args.gate.exists():
        raise SystemExit(f"{args.gate} not found: run `uv run python scripts/pick_gate_samples.py` first")
    with args.scales.open(newline="") as f:
        folders = download_order(list(csv.DictReader(f)))
    with args.gate.open(newline="") as f:
        gate = {r["sample"] for r in csv.DictReader(f)}
    if args.only:
        folders = [f for f in folders if f in args.only]
    failed = run_benchmark(folders, args.data, args.out, gate, TUNING_SAMPLES, _commit())
    if failed:
        raise SystemExit(f"{len(failed)} sample(s) failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
