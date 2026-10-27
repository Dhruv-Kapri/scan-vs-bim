"""Resumable, chunked HTTP range downloads (Zenodo is slow and flaky).

`read_range(start, end_inclusive) -> bytes` is the only network seam, so the extraction
logic can be tested against an in-memory zip.
"""

import hashlib
import struct
import time
import zlib
import zipfile
from pathlib import Path
from typing import Callable

import requests

ReadRange = Callable[[int, int], bytes]
CHUNK = 6 * 1024 * 1024
LOCAL_HEADER = 30


def http_range_reader(url: str, retries: int = 8, timeout: int = 60) -> ReadRange:
    """Range reader over `requests` with exponential backoff; fails on short reads."""

    def read_range(start: int, end: int) -> bytes:
        want = end - start + 1
        for attempt in range(retries):
            try:
                r = requests.get(
                    url, headers={"Range": f"bytes={start}-{end}"}, timeout=timeout
                )
                if r.status_code == 206 and len(r.content) == want:
                    return r.content
                err = f"HTTP {r.status_code}, {len(r.content)}/{want} bytes"
            except requests.RequestException as e:
                err = repr(e)
            wait = min(2**attempt, 60)
            print(f"  retry {attempt + 1}/{retries} for bytes {start}-{end} ({err}); sleep {wait}s")
            time.sleep(wait)
        raise RuntimeError(f"giving up on bytes {start}-{end} of {url}")

    return read_range


def download_range(
    read_range: ReadRange, start: int, length: int, part: Path, chunk_size: int = CHUNK, label: str = ""
) -> None:
    """Fetch `length` bytes from `start` into `part`, resuming from its current size."""
    part.parent.mkdir(parents=True, exist_ok=True)
    have = part.stat().st_size if part.exists() else 0
    if have > length:
        part.unlink()
        have = 0
    with open(part, "ab") as f:
        while have < length:
            n = min(chunk_size, length - have)
            data = read_range(start + have, start + have + n - 1)
            if len(data) != n:
                raise IOError(f"short read: {len(data)}/{n} bytes at {start + have}")
            f.write(data)
            f.flush()
            have += len(data)
            print(f"  {label} {have / 1e6:.1f}/{length / 1e6:.1f} MB", flush=True)


def extract_zip_member(
    read_range: ReadRange, info: zipfile.ZipInfo, dest: Path, chunk_size: int = CHUNK
) -> None:
    """Extract one zip member to `dest` using only ranged reads; verifies size and CRC32."""
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size == info.file_size:
        print(f"skip {dest} (exists)")
        return
    # Local header lengths can differ from the central directory's.
    hdr = read_range(info.header_offset, info.header_offset + LOCAL_HEADER - 1)
    if hdr[:4] != b"PK\x03\x04":
        raise ValueError(f"bad local header signature at {info.header_offset}")
    name_len, extra_len = struct.unpack("<HH", hdr[26:30])
    data_start = info.header_offset + LOCAL_HEADER + name_len + extra_len

    part = dest.with_name(dest.name + ".part")
    download_range(read_range, data_start, info.compress_size, part, chunk_size, dest.name)

    if info.compress_type == zipfile.ZIP_DEFLATED:
        inflater = zlib.decompressobj(-15)
    elif info.compress_type == zipfile.ZIP_STORED:
        inflater = None
    else:
        raise ValueError(f"unsupported compression method {info.compress_type}")

    out = dest.with_name(dest.name + ".out")
    crc = size = 0
    with open(part, "rb") as src, open(out, "wb") as dst:
        while block := src.read(1 << 20):
            block = inflater.decompress(block) if inflater else block
            crc = zlib.crc32(block, crc)
            size += len(block)
            dst.write(block)
        if inflater:
            block = inflater.flush()
            crc = zlib.crc32(block, crc)
            size += len(block)
            dst.write(block)
    if crc != info.CRC or size != info.file_size:
        out.unlink()
        part.unlink()  # corrupt download: next run refetches from scratch
        raise ValueError(f"CRC/size mismatch for {dest.name}: crc {crc:#x} vs {info.CRC:#x}, size {size} vs {info.file_size}")
    out.replace(dest)
    part.unlink()
    print(f"ok   {dest} ({size / 1e6:.1f} MB)")


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def fetch_file(read_range: ReadRange, size: int, md5: str, dest: Path, chunk_size: int = CHUNK) -> None:
    """Download a whole file in ranged chunks (resumable), verifying md5."""
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size == size and md5_of(dest) == md5:
        print(f"skip {dest} (md5 ok)")
        return
    part = dest.with_name(dest.name + ".part")
    download_range(read_range, 0, size, part, chunk_size, dest.name)
    if md5_of(part) != md5:
        part.unlink()
        raise ValueError(f"md5 mismatch for {dest.name}")
    part.replace(dest)
    print(f"ok   {dest}")
