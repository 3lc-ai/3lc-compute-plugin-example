# Copyright 2026 3LC Inc.
# SPDX-License-Identifier: Apache-2.0
"""The mission patch — a pixel-art PNG generated with nothing but the stdlib.

Exists to demonstrate a **binary** custom route (``GET /api/plugins/example/patch.png``,
see ``routes.py``): the content type a plugin sets is preserved end-to-end through the
worker reverse-proxy, so a plugin can serve images, archives, or model files like any
other web app. Pure ``zlib``/``struct`` so the example keeps zero dependencies.
"""

from __future__ import annotations

import struct
import zlib
from functools import lru_cache

# 16×16 art, one char per pixel. Keys into _PALETTE; "." is transparent.
_ART = (
    "................",
    ".......oo.......",
    "......owwo......",
    "......owwo......",
    ".....owwwwo.....",
    ".....owccwo.....",
    ".....owccwo.....",
    ".....owwwwo.....",
    "....owwwwwwo....",
    "....owwwwwwo....",
    "...rowwwwwwor...",
    "..rrowwwwwworr..",
    ".rroooooooooorr.",
    "....ff.ff.ff....",
    ".....f.ff.f.....",
    "......f..f......",
)

_PALETTE = {
    "o": (36, 41, 51, 255),  # hull outline
    "w": (236, 239, 244, 255),  # hull
    "c": (100, 181, 246, 255),  # window
    "r": (229, 87, 74, 255),  # fins
    "f": (255, 167, 38, 255),  # exhaust
    ".": (0, 0, 0, 0),  # transparent
}

_SCALE = 6  # 16px art → 96px patch


def _chunk(tag: bytes, payload: bytes) -> bytes:
    """Assemble one PNG chunk: length, tag, payload, CRC."""
    return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload))


@lru_cache(maxsize=1)
def mission_patch_png() -> bytes:
    """Render the patch as PNG bytes (cached — the art does not change mid-mission)."""
    size = len(_ART) * _SCALE
    raw = bytearray()
    for row in _ART:
        scanline = bytearray()
        for char in row:
            scanline += bytes(_PALETTE[char]) * _SCALE
        for _ in range(_SCALE):
            raw += b"\x00" + scanline  # filter byte 0 (None) + RGBA pixels
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return b"".join((
        b"\x89PNG\r\n\x1a\n",
        _chunk(b"IHDR", header),
        _chunk(b"IDAT", zlib.compress(bytes(raw), 9)),
        _chunk(b"IEND", b""),
    ))
