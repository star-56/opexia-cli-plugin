# pxcore/renderer/png.py — a minimal, correct PNG encoder over the standard library only.
#
# Why hand-rolled: the whole product's claim is "no bloat, control every layer, no external
# dep in the core." A vision model reads a crisp 8-bit greyscale bitmap perfectly well, and
# encoding one is ~40 lines of well-specified format work over `zlib` (stdlib). Pulling
# Pillow to do this would contradict the design for no benefit the encoder can't give.
#
# Format: PNG (RFC 2083). 8-bit greyscale, no interlace, filter 0 (None) per scanline.
from __future__ import annotations

import struct
import zlib
from typing import List

_SIG = b"\x89PNG\r\n\x1a\n"


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def encode_gray8(width: int, height: int, rows: List[bytearray]) -> bytes:
    """rows: `height` bytearrays, each of length `width`, one 0..255 grey byte per pixel."""
    if len(rows) != height:
        raise ValueError(f"expected {height} rows, got {len(rows)}")
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)  # 8bpp, greyscale(0)
    raw = bytearray()
    for r in rows:
        if len(r) != width:
            raise ValueError("row width mismatch")
        raw.append(0)            # filter type 0 (None) for this scanline
        raw.extend(r)
    idat = zlib.compress(bytes(raw), 9)
    return _SIG + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def decode_gray8_dims(png: bytes) -> tuple:
    """Read back (width, height) from our own PNG — used by tests/verification to prove the
    bytes we emit are a real, parseable PNG rather than assuming it."""
    if png[:8] != _SIG:
        raise ValueError("not a PNG")
    # first chunk after signature is IHDR
    (length,) = struct.unpack(">I", png[8:12])
    tag = png[12:16]
    if tag != b"IHDR":
        raise ValueError("first chunk is not IHDR")
    w, h = struct.unpack(">II", png[16:24])
    return w, h
