"""
Turning what the bar's log dump holds into lines, and finding things in them.
"""

from __future__ import annotations

import bz2
import gzip
import io
import lzma
import tarfile
import zipfile

import pytest
from examples.manager.logs import MAX_UNPACKED, LogBuffer, unpack
from examples.manager.model import ManagerError

LOG = "boot ok\r\nwifi up\r\nERROR: sd card\r\n"


def _tar(files: dict[str, str]) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as archive:
        for name, text in files.items():
            body = text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
    return out.getvalue()


def _zip(files: dict[str, str]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return out.getvalue()


def test_plain_text_is_text() -> None:
    assert unpack(LOG.encode()) == LOG


@pytest.mark.parametrize("pack", [gzip.compress, bz2.compress, lzma.compress])
def test_a_packed_log_is_unpacked_whatever_it_is_called(pack) -> None:
    assert unpack(pack(LOG.encode())) == LOG


def test_a_zip_of_several_files_reads_as_one_with_each_named() -> None:
    text = unpack(_zip({"a.txt": "one", "b.txt": "two"}))

    assert text == "=== a.txt ===\none\n=== b.txt ===\ntwo"


def test_a_tar_even_a_packed_one_reads_the_same_way() -> None:
    packed = gzip.compress(_tar({"a.txt": "one", "dir/b.txt": "two"}))

    assert unpack(packed) == "=== a.txt ===\none\n=== dir/b.txt ===\ntwo"


def test_bytes_that_are_not_text_are_shown_not_refused() -> None:
    assert unpack(b"ok \xff\xfe bytes") == "ok �� bytes"


def test_a_file_that_says_it_is_packed_and_is_not_says_so() -> None:
    with pytest.raises(ManagerError, match="could not be unpacked"):
        unpack(b"\x1f\x8b" + b"not really gzip")


def test_a_bomb_is_refused_rather_than_unpacked() -> None:
    bomb = gzip.compress(b"\0" * (MAX_UNPACKED + 1024), compresslevel=1)

    with pytest.raises(ManagerError, match="64 MiB"):
        unpack(bomb)


def test_lines_are_split_on_either_line_ending() -> None:
    assert LogBuffer.of(LOG).lines == ["boot ok", "wifi up", "ERROR: sd card"]


@pytest.fixture
def buffer() -> LogBuffer:
    return LogBuffer(["Alpha", "beta", "ALPHA beta", "gamma", "alpha"])


def test_a_search_ignores_case_and_starts_where_it_is_told(buffer: LogBuffer) -> None:
    assert buffer.find("alpha", 0) == 0
    assert buffer.find("alpha", 1) == 2
    assert buffer.find("alpha", 3) == 4


def test_a_search_wraps_round_the_end_in_either_direction(buffer: LogBuffer) -> None:
    assert buffer.find("beta", 3) == 1
    assert buffer.find("gamma", 4, backwards=True) == 3
    assert buffer.find("beta", 0, backwards=True) == 2
    assert buffer.find("alpha", 1, backwards=True) == 0


def test_nothing_found_is_none(buffer: LogBuffer) -> None:
    assert buffer.find("zeta", 0) is None
    assert buffer.find("", 0) is None
    assert LogBuffer([]).find("a", 0) is None


def test_lines_with_a_match_are_counted_once_each(buffer: LogBuffer) -> None:
    assert buffer.count("alpha") == 3
    assert buffer.count("beta") == 2
    assert buffer.count("") == 0
