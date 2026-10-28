"""Stream the CRAS annotated-scan zip into a voxel-subsampled .npz cache (never extracts the member)."""

import argparse
import resource
import sys
from pathlib import Path

from scan_vs_bim.cras_cache import build_cache

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", type=Path, default=ROOT / "data" / "cras" / "craslabannotated.zip")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "cras" / "cras_voxel_1cm.npz")
    ap.add_argument("--voxel", type=float, default=0.01, help="voxel edge in metres")
    args = ap.parse_args()

    meta = build_cache(args.zip, args.out, voxel=args.voxel)

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_mb = rss / 1e6 if sys.platform == "darwin" else rss / 1e3  # bytes on macOS, KB on Linux
    print(f"points read: {meta['points_read']} (declared {meta['points_declared']})")
    print(f"points kept: {meta['points_kept']}")
    print(f"extent: {meta['extent_min']} .. {meta['extent_max']}")
    print(f"peak RSS: {rss_mb:.0f} MB")


if __name__ == "__main__":
    main()
