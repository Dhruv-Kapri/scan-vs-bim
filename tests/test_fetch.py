import io
import logging
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import requests

from scan_vs_bim import fetch
from scan_vs_bim.fetch import data_start, extract_zip_member


def make_zip(path):
    payloads = {
        "dir/deflated.bin": (os.urandom(2000) + b"abc" * 5000, zipfile.ZIP_DEFLATED),
        "dir/stored.bin": (os.urandom(3000), zipfile.ZIP_STORED),
    }
    with zipfile.ZipFile(path, "w") as z:
        for name, (data, method) in payloads.items():
            z.writestr(zipfile.ZipInfo(name), data, compress_type=method)
    return {n: d for n, (d, _) in payloads.items()}


def reader_for(blob, calls=None):
    def read_range(start, end_inclusive):
        if calls is not None:
            calls.append((start, end_inclusive))
        return blob[start : end_inclusive + 1]

    return read_range


@pytest.mark.parametrize("name", ["dir/deflated.bin", "dir/stored.bin"])
def test_extract_roundtrip_chunked(tmp_path: Path, name: str) -> None:
    zpath = tmp_path / "t.zip"
    originals = make_zip(zpath)
    blob = zpath.read_bytes()
    info = zipfile.ZipFile(zpath).getinfo(name)
    calls: list[tuple[int, int]] = []
    dest = tmp_path / "out" / "x.bin"
    extract_zip_member(reader_for(blob, calls), info, dest, chunk_size=100)
    assert dest.read_bytes() == originals[name]
    assert not dest.with_name("x.bin.part").exists()
    assert max(e - s + 1 for s, e in calls) <= 100  # every ranged read, the 30-byte header included, honours chunk_size
    assert len(calls) > 2  # the header and more than one data chunk


def test_resume_from_part_file(tmp_path):
    zpath = tmp_path / "t.zip"
    originals = make_zip(zpath)
    blob = zpath.read_bytes()
    info = zipfile.ZipFile(zpath).getinfo("dir/deflated.bin")
    dest = tmp_path / "x.bin"
    # Pre-seed a partial download: first 120 compressed bytes.
    start = data_start(reader_for(blob), info)
    dest.with_name("x.bin.part").write_bytes(blob[start : start + 120])
    calls: list[tuple[int, int]] = []
    extract_zip_member(reader_for(blob, calls), info, dest, chunk_size=100)
    assert dest.read_bytes() == originals["dir/deflated.bin"]
    assert min(s for s, _ in calls[1:]) >= start + 120


def test_skip_when_complete(tmp_path):
    zpath = tmp_path / "t.zip"
    originals = make_zip(zpath)
    info = zipfile.ZipFile(zpath).getinfo("dir/stored.bin")
    dest = tmp_path / "x.bin"
    dest.write_bytes(originals["dir/stored.bin"])

    def boom(s, e):
        raise AssertionError("should not fetch")

    extract_zip_member(boom, info, dest, chunk_size=100)


def test_corruption_fails_crc(tmp_path):
    zpath = tmp_path / "t.zip"
    make_zip(zpath)
    blob = bytearray(zpath.read_bytes())
    info = zipfile.ZipFile(zpath).getinfo("dir/stored.bin")
    blob[data_start(reader_for(blob), info) + 10] ^= 0xFF
    dest = tmp_path / "x.bin"
    with pytest.raises(ValueError, match="CRC"):
        extract_zip_member(reader_for(bytes(blob)), info, dest, chunk_size=100)
    assert not dest.exists()


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(requests.ConnectionError("boom"), id="connection error"),
        pytest.param(SimpleNamespace(status_code=504, content=b"504!"), id="HTTP 504"),  # a body of the asked length: only the status can reject it
        pytest.param(SimpleNamespace(status_code=206, content=b"ab"), id="short read"),
    ],
)
def test_a_failed_range_read_is_retried_and_logged_on_the_fetch_logger(failure: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    # Zenodo returns 504s and short reads. Notebook 05a counts retries from the records of the "scan_vs_bim.fetch" logger.
    responses = iter([failure, SimpleNamespace(status_code=206, content=b"abcd")])

    def get(*args: Any, **kwargs: Any) -> Any:
        r = next(responses)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(fetch.requests, "get", get)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    with caplog.at_level(logging.INFO, logger="scan_vs_bim.fetch"):
        assert fetch.http_range_reader("http://x")(0, 3) == b"abcd"
    assert [r.name for r in caplog.records if "retry" in r.getMessage()] == ["scan_vs_bim.fetch"]
