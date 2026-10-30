import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fetch_data.py"


@pytest.fixture
def fetch_data(monkeypatch):
    spec = importlib.util.spec_from_file_location("fetch_data", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fetched, extracted = [], []

    class FakeRemoteZip:
        def __init__(self, url):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def infolist(self):
            info = SimpleNamespace(filename=mod.SAMPLE_DIR + "scan.txt", is_dir=lambda: False)
            return [info]

    monkeypatch.setattr(mod, "http_range_reader", lambda url: url)
    monkeypatch.setattr(mod, "fetch_file", lambda reader, size, md5, dest: fetched.append(Path(dest).name))
    monkeypatch.setattr(mod, "RemoteZip", FakeRemoteZip)
    monkeypatch.setattr(mod, "extract_zip_member", lambda reader, info, dest: extracted.append(Path(dest).name))
    return mod, fetched, extracted


def test_default_skips_the_scan_zip(fetch_data):
    mod, fetched, extracted = fetch_data
    mod.main([])
    assert fetched == ["craslabbim.ifc"]
    assert extracted == ["scan.txt"]


def test_with_scan_fetches_the_zip(fetch_data):
    mod, fetched, extracted = fetch_data
    mod.main(["--with-scan"])
    assert fetched == ["craslabbim.ifc", "craslabannotated.zip"]
    assert extracted == ["scan.txt"]
