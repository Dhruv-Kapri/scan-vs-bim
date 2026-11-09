import resource
import sys
from types import SimpleNamespace

import pytest

from scan_vs_bim.memory import peak_rss_gb


@pytest.mark.parametrize(("platform", "ru_maxrss"), [("darwin", 1.5e9), ("linux", 1.5e6)], ids=["macOS: bytes", "Linux: kilobytes"])
def test_peak_rss_is_in_gigabytes_whatever_unit_the_platform_reports(platform: str, ru_maxrss: float, monkeypatch: pytest.MonkeyPatch) -> None:
    # getrusage(2) gives ru_maxrss in bytes on macOS and in KB on Linux. Faked rather than measured: the old 0.01..100 GB bound
    # passed a 1e3 unit error on a lone run (0.02 GB peak), and a measured allocation is paged out unpredictably on an 8 GB machine.
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(resource, "getrusage", lambda who: SimpleNamespace(ru_maxrss=ru_maxrss))
    assert peak_rss_gb() == pytest.approx(1.5)
