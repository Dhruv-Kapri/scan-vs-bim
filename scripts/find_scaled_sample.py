"""Find the smallest PC2Model sample with scale != 1 (reads only the transform files), then fetch it.

Writes outputs/pc2model_scales.csv. Transform texts are cached in data/pc2model/transforms/.
"""

import argparse
import csv
from pathlib import Path

from remotezip import RemoteZip

from scan_vs_bim.fetch import extract_zip_member, http_range_reader
from scan_vs_bim.pc2model import URL as PC2MODEL_URL, cached_scales, group_samples, pick_smallest_scaled

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data" / "pc2model"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true", help="only list scales, skip the download")
    args = ap.parse_args()

    with RemoteZip(PC2MODEL_URL) as z:  # reads only the central directory
        infos = z.infolist()
    samples = group_samples(infos)
    reader = http_range_reader(PC2MODEL_URL)

    scales = cached_scales(reader, samples, DATA / "transforms")

    out = REPO / "outputs" / "pc2model_scales.csv"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sample", "category", "compressed_mb", "scale"])
        for s in sorted(samples, key=lambda s: s.compressed_size):
            category = s.folder.split("/")[1]  # PC2Model_v1.4/<category>/<sample>
            w.writerow([s.folder, category, f"{s.compressed_size / 1e6:.2f}", f"{scales[s.folder]:.6f}"])
    print(f"wrote {out}")

    chosen = pick_smallest_scaled(samples, scales)
    print(f"chosen: {chosen.folder} ({chosen.compressed_size / 1e6:.1f} MB, scale {scales[chosen.folder]:.4f})")
    if args.no_fetch:
        return
    dest = DATA / Path(chosen.folder).name
    members = [i for i in infos if i.filename.startswith(chosen.folder + "/") and not i.is_dir()]
    for info in members:
        extract_zip_member(reader, info, dest / Path(info.filename).name)


if __name__ == "__main__":
    main()
