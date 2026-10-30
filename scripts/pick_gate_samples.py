"""Choose the 9 PC2Model samples for the registration gate (notebook 05a); reads only the zip directory and transforms.

Per category (house, simulated indoor, real indoor): the smallest scaled sample, the smallest unscaled sample, then
the next smallest remaining. Writes outputs/05a/gate_samples.csv. Downloads no point clouds.
"""

import csv
from pathlib import Path

from remotezip import RemoteZip

from scan_vs_bim.fetch import http_range_reader
from scan_vs_bim.pc2model import URL as PC2MODEL_URL, cached_scales, group_samples, pick_gate_samples

REPO = Path(__file__).resolve().parent.parent
GROUPS = {  # PC2Model category folder -> label used in the notebook
    "house": "house",
    "indoor_modelling": "simulated indoor",
    "ISPRS_indoor_modeling_benchmark": "real indoor",
}


def main() -> None:
    with RemoteZip(PC2MODEL_URL) as z:  # reads only the central directory
        samples = group_samples(z.infolist())
    scales = cached_scales(http_range_reader(PC2MODEL_URL), samples, REPO / "data" / "pc2model" / "transforms")
    chosen = pick_gate_samples(samples, scales, list(GROUPS))

    out = REPO / "outputs" / "05a" / "gate_samples.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sample", "category", "label", "compressed_mb", "scale"])
        for s in chosen:
            category = s.folder.split("/")[1]
            w.writerow([s.folder, category, GROUPS[category], f"{s.compressed_size / 1e6:.2f}", f"{scales[s.folder]:.6f}"])
            print(f"{GROUPS[category]:17s}{Path(s.folder).name:70s}{s.compressed_size / 1e6:8.1f} MB  scale {scales[s.folder]:.4f}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
