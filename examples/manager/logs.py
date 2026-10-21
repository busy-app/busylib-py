"""
The bar's log, as text a person can read and search.

The bar writes what it logged to a file on its storage when asked. This turns
what comes back into lines - unpacking it first if it is packed, which a dump
may be - and finds things in them. Nothing here touches the bar or a terminal.
"""

from __future__ import annotations

import bz2
import gzip
import io
import lzma
import tarfile
import zipfile
from dataclasses import dataclass

from .model import ManagerError

# A log is text and a few megabytes at most; a packed file that unpacks to far
# more than that is not one, and reading it all would take the machine with it.
MAX_UNPACKED = 64 * 1024 * 1024


def _limited(read, what: str) -> bytes:
    data = read(MAX_UNPACKED + 1)
    if len(data) > MAX_UNPACKED:
        raise ManagerError(f"the {what} unpacks to more than 64 MiB; not a log")
    return data


def unpack(data: bytes) -> str:
    """
    The text in a dump, whether it is plain or packed (gzip, bzip2, xz, zip or
    tar, as the first bytes say - not as a file name claims).

    An archive of several files is read as one, each under a line naming it.
    """
    try:
        if data[:2] == b"\x1f\x8b":
            raw = _limited(gzip.GzipFile(fileobj=io.BytesIO(data)).read, "log")
        elif data[:3] == b"BZh":
            raw = _limited(bz2.BZ2File(io.BytesIO(data)).read, "log")
        elif data[:6] == b"\xfd7zXZ\x00":
            raw = _limited(lzma.LZMAFile(io.BytesIO(data)).read, "log")
        else:
            raw = data
        if raw[:4] == b"PK\x03\x04":
            raw = _zip(raw)
        elif raw[257:262] == b"ustar":
            raw = _tar(raw)
    except (
        OSError,
        EOFError,
        zipfile.BadZipFile,
        tarfile.TarError,
        lzma.LZMAError,
    ) as err:
        raise ManagerError(f"the log could not be unpacked ({err})") from err
    return raw.decode("utf-8", errors="replace")


def _zip(raw: bytes) -> bytes:
    parts: list[bytes] = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if info.file_size > MAX_UNPACKED:
                raise ManagerError(f"{info.filename} unpacks to more than 64 MiB")
            parts.append(f"=== {info.filename} ===\n".encode() + archive.read(info))
    return b"\n".join(parts)


def _tar(raw: bytes) -> bytes:
    parts: list[bytes] = []
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive:
            if not member.isfile():
                continue
            if member.size > MAX_UNPACKED:
                raise ManagerError(f"{member.name} unpacks to more than 64 MiB")
            body = archive.extractfile(member)
            parts.append(
                f"=== {member.name} ===\n".encode() + (body.read() if body else b"")
            )
    return b"\n".join(parts)


@dataclass
class LogBuffer:
    """
    A log, as lines.
    """

    lines: list[str]

    @classmethod
    def of(cls, text: str) -> LogBuffer:
        return cls(text.splitlines())

    def __len__(self) -> int:
        return len(self.lines)

    def find(self, needle: str, start: int, *, backwards: bool = False) -> int | None:
        """
        The next line holding `needle`, ignoring case, counting from `start`
        (itself included) and wrapping round past either end. None if no line
        has it.
        """
        if not needle or not self.lines:
            return None
        wanted = needle.lower()
        total = len(self.lines)
        step = -1 if backwards else 1
        for offset in range(total):
            index = (start + step * offset) % total
            if wanted in self.lines[index].lower():
                return index
        return None

    def count(self, needle: str) -> int:
        wanted = needle.lower()
        return sum(wanted in line.lower() for line in self.lines) if wanted else 0
