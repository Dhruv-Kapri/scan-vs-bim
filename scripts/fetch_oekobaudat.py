"""Download the ÖKOBAUDAT datasets named in notebooks/04b_material_mapping.csv into data/oekobaudat/.

Each mapped process dataset and its reference-flow dataset is saved unmodified (ILCD+EPD XML), as
data/oekobaudat/processes/<uuid>.xml and data/oekobaudat/flows/<uuid>.xml. Existing files are skipped.
ÖKOBAUDAT allows only unmodified copies, to be passed on with the source named, so this data stays
in gitignored data/ and is never committed.
"""

import csv
import sys
import time
from pathlib import Path

import requests

from scan_vs_bim.oekobaudat import reference_flow_uuid

ROOT = Path(__file__).parents[1]
MAPPING = ROOT / "notebooks" / "04b_material_mapping.csv"
DEST = ROOT / "data" / "oekobaudat"
BASE = "https://www.oekobaudat.de/OEKOBAU.DAT/resource"  # soda4LCA service interface; by uuid it serves the latest version


def fetch(kind: str, uuid: str, retries: int = 6) -> Path:
    path = DEST / kind / f"{uuid}.xml"
    if path.exists():
        return path
    for attempt in range(retries):
        try:
            r = requests.get(f"{BASE}/{kind}/{uuid}", params={"format": "xml"}, timeout=60)
            if r.status_code == 200 and r.content.lstrip().startswith(b"<?xml"):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.with_suffix(".part").write_bytes(r.content)
                path.with_suffix(".part").replace(path)
                return path
            err = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            err = repr(e)
        wait = min(2**attempt, 30)
        print(f"  retry {attempt + 1}/{retries} for {kind}/{uuid} ({err}); sleep {wait}s")
        time.sleep(wait)
    raise RuntimeError(f"giving up on {kind}/{uuid}")


def main() -> int:
    with open(MAPPING, newline="", encoding="utf-8") as f:
        uuids = sorted({r["oekobaudat_uuid"] for r in csv.DictReader(f) if r["oekobaudat_uuid"]})
    for uuid in uuids:
        existed = (DEST / "processes" / f"{uuid}.xml").exists()
        process = fetch("processes", uuid)
        fetch("flows", reference_flow_uuid(process.read_text(encoding="utf-8")))
        print(f"{uuid}: {'already there' if existed else 'downloaded'}")
    print(f"{len(uuids)} datasets in {DEST.relative_to(ROOT)}. Source: ÖKOBAUDAT (BBSR/BMWSB), https://www.oekobaudat.de")
    return 0


if __name__ == "__main__":
    sys.exit(main())
