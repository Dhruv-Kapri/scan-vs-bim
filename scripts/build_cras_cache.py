"""Stream the CRAS annotated-scan zip into a voxel-subsampled .npz cache (never extracts the member)."""

import argparse
import logging
from pathlib import Path

from scan_vs_bim.cras_cache import build_cache
from scan_vs_bim.memory import peak_rss_gb

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", type=Path, default=ROOT / "data" / "cras" / "craslabannotated.zip")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "cras" / "cras_voxel_1cm.npz")
    ap.add_argument("--voxel", type=float, default=0.01, help="voxel edge in metres")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not args.zip.exists():
        raise SystemExit(f"{args.zip} not found; run `uv run python scripts/fetch_data.py --with-scan` first")

    meta = build_cache(args.zip, args.out, voxel=args.voxel)

    print(f"points read: {meta['points_read']} (declared {meta['points_declared']})")
    print(f"points kept: {meta['points_kept']}")
    print(f"extent: {meta['extent_min']} .. {meta['extent_max']}")
    print(f"peak RSS: {peak_rss_gb() * 1e3:.0f} MB")


if __name__ == "__main__":
    main()
