"""Fetch all 137 PC2Model samples (about 8.9 GB) into data/pc2model/<sample>/ (issue #36).

The sample list is outputs/pc2model_scales.csv (scripts/find_scaled_sample.py --no-fetch writes it), smallest first.
Building categories (house, indoor_modelling, ISPRS_indoor_modeling_benchmark) come first, then the object
categories. Resumable and idempotent: partial files resume, complete ones are skipped. It runs for hours at Zenodo
speeds, so run it detached (see the cras-cache pattern in CLAUDE.md).
"""

import argparse
import csv
import logging
from pathlib import Path

from remotezip import RemoteZip

from scan_vs_bim.fetch import http_range_reader
from scan_vs_bim.pc2model import URL as PC2MODEL_URL
from scan_vs_bim.pc2model import download_order, fetch_samples

REPO = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", type=Path, default=REPO / "outputs" / "pc2model_scales.csv")
    ap.add_argument("--out", type=Path, default=REPO / "data" / "pc2model")
    args = ap.parse_args(argv)
    if not args.csv.exists():
        raise SystemExit(f"{args.csv} not found: run `uv run python scripts/find_scaled_sample.py --no-fetch` first")
    with args.csv.open(newline="") as f:
        rows = list(csv.DictReader(f))
    with RemoteZip(PC2MODEL_URL) as z:  # reads only the central directory
        infos = z.infolist()
    fetch_samples(http_range_reader(PC2MODEL_URL), infos, download_order(rows), args.out)


if __name__ == "__main__":
    main()
