"""Fetch the PC2Model samples used to tune registration in the Phase 0.5 tuning week (issue #20).

None of them is a gate sample (outputs/05a/gate_samples.csv), and none shares a building with one: the simulated and
real versions of the UVigo, UoM, TUBS1, TUBS2 and Fire Brigade buildings are all excluded, because a gate sample of the
same building has the same model. So the simulated indoor pick is GM (unscaled), and real GM (scaled 1.98) is the real
indoor pick. house_6 is the smallest scaled house outside the gate. Resumable and idempotent, like fetch_data.py.
"""

from pathlib import Path

from remotezip import RemoteZip

from scan_vs_bim.fetch import extract_zip_member, http_range_reader
from scan_vs_bim.pc2model import URL as PC2MODEL_URL

DATA = Path(__file__).resolve().parent.parent / "data" / "pc2model"

TUNING_SAMPLES = [
    "PC2Model_v1.4/house/house_6-sketchfab",  # 172 MB, scale 1.789
    "PC2Model_v1.4/indoor_modelling/indoor_modelling_5-ISPRS_indoor_modelling-GM",  # 222 MB, scale 1
    "PC2Model_v1.4/ISPRS_indoor_modeling_benchmark/real-indoor_modelling_5-ISPRS_indoor_modelling-GM",  # 311 MB, 1.984
]


def main() -> None:
    with RemoteZip(PC2MODEL_URL) as z:  # reads only the central directory
        infos = z.infolist()
    reader = http_range_reader(PC2MODEL_URL)
    for folder in TUNING_SAMPLES:
        for info in infos:
            if info.filename.startswith(folder + "/") and not info.is_dir():
                extract_zip_member(reader, info, DATA / Path(folder).name / Path(info.filename).name)
        print(f"done: {folder}", flush=True)


if __name__ == "__main__":
    main()
