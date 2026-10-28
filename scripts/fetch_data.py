"""Fetch the Stage 0 data: the CRAS IFC and annotated scan zip (not extracted) and one PC2Model indoor sample."""

from pathlib import Path

from remotezip import RemoteZip

from scan_vs_bim.fetch import extract_zip_member, fetch_file, http_range_reader
from scan_vs_bim.pc2model import URL as PC2MODEL_URL

ROOT = Path(__file__).resolve().parent.parent / "data"

CRAS_URL = "https://zenodo.org/api/records/7948116/files/craslabbim.ifc/content"
CRAS_SIZE = 67553572
CRAS_MD5 = "e20658f0d2d9e13c62363169b7fa3193"

CRAS_SCAN_URL = "https://zenodo.org/api/records/7948116/files/craslabannotated.zip/content"
CRAS_SCAN_SIZE = 4267281425
CRAS_SCAN_MD5 = "e5ecedab8f2a1d1f91861a3aec028a72"

SAMPLE_DIR = "PC2Model_v1.4/ISPRS_indoor_modeling_benchmark/real-indoor_modelling_3-ISPRS_indoor_modelling-UVigo/"


def main() -> None:
    fetch_file(http_range_reader(CRAS_URL), CRAS_SIZE, CRAS_MD5, ROOT / "cras" / "craslabbim.ifc")
    # 26.8 GB unzipped: never extract; scripts/build_cras_cache.py streams it.
    fetch_file(
        http_range_reader(CRAS_SCAN_URL), CRAS_SCAN_SIZE, CRAS_SCAN_MD5, ROOT / "cras" / "craslabannotated.zip"
    )

    with RemoteZip(PC2MODEL_URL) as z:  # reads only the central directory
        members = [i for i in z.infolist() if i.filename.startswith(SAMPLE_DIR) and not i.is_dir()]
    reader = http_range_reader(PC2MODEL_URL)
    sample = ROOT / "pc2model" / Path(SAMPLE_DIR).name
    for info in members:
        extract_zip_member(reader, info, sample / Path(info.filename).name)


if __name__ == "__main__":
    main()
