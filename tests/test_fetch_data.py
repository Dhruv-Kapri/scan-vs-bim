import importlib.util
import logging
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Literal

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fetch_data.py"


@pytest.fixture
def fetch_data(monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, list[str], list[str]]:
    spec = importlib.util.spec_from_file_location("fetch_data", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fetched: list[str] = []
    extracted: list[str] = []

    class FakeRemoteZip:
        def __init__(self, url: str) -> None:
            pass

        def __enter__(self) -> "FakeRemoteZip":
            return self

        def __exit__(self, *exc: object) -> Literal[False]:
            return False

        def infolist(self) -> list[SimpleNamespace]:
            info = SimpleNamespace(filename=mod.SAMPLE_DIR + "scan.txt", is_dir=lambda: False)
            return [info]

    monkeypatch.setattr(mod, "http_range_reader", lambda url: url)
    monkeypatch.setattr(mod, "fetch_file", lambda reader, size, md5, dest: fetched.append(Path(dest).name))
    monkeypatch.setattr(mod, "RemoteZip", FakeRemoteZip)
    monkeypatch.setattr(mod, "extract_zip_member", lambda reader, info, dest: extracted.append(Path(dest).name))
    return mod, fetched, extracted


def test_default_skips_the_scan_zip(fetch_data: tuple[ModuleType, list[str], list[str]]) -> None:
    mod, fetched, extracted = fetch_data
    mod.main([])
    assert fetched == ["craslabbim.ifc"]
    assert extracted == ["scan.txt"]


def test_with_scan_fetches_the_zip(fetch_data: tuple[ModuleType, list[str], list[str]]) -> None:
    mod, fetched, extracted = fetch_data
    mod.main(["--with-scan"])
    assert fetched == ["craslabbim.ifc", "craslabannotated.zip"]
    assert extracted == ["scan.txt"]


class _Stop(Exception):
    pass


@pytest.mark.parametrize("script", ["fetch_tuning_samples.py", "make_tuning_slice.py"])
def test_scripts_log_at_info_like_fetch_data(script: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Library code logs through `logging` (#16); a script must configure INFO or its progress lines are silent."""
    configured: dict[str, object] = {}

    def basic_config(**kwargs: object) -> None:
        configured.update(kwargs)
        raise _Stop  # configuring is the first thing main() does; skip the real work

    spec = importlib.util.spec_from_file_location(script[:-3], SCRIPT.with_name(script))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(logging, "basicConfig", basic_config)
    with pytest.raises(_Stop):
        mod.main()
    assert configured["level"] == logging.INFO
