#!/usr/bin/env python3
"""Generate AGENTS HQ PNG / ICO / ICNS assets from a drawn robot mark (no pip deps)."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
MAC_RES = ROOT / "macos" / "AGENTS HQ.app" / "Contents" / "Resources"


def _draw(size: int) -> bytes:
    """RGBA pixels for a simple green robot face matching static/icon.svg."""
    px = bytearray(size * size * 4)
    green = (63, 174, 138, 255)
    white = (255, 255, 255, 255)
    screen = (20, 24, 32, 255)
    clear = (0, 0, 0, 0)

    def put(x: int, y: int, rgba):
        if 0 <= x < size and 0 <= y < size:
            i = (y * size + x) * 4
            px[i : i + 4] = bytes(rgba)

    def fill_round_rect(x0, y0, x1, y1, r, rgba):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                dx = 0 if x0 + r <= x <= x1 - r else min(abs(x - (x0 + r)), abs(x - (x1 - r)))
                dy = 0 if y0 + r <= y <= y1 - r else min(abs(y - (y0 + r)), abs(y - (y1 - r)))
                if dx == 0 or dy == 0 or dx * dx + dy * dy <= r * r:
                    put(x, y, rgba)

    def fill_circle(cx, cy, rad, rgba):
        rr = rad * rad
        for y in range(cy - rad, cy + rad + 1):
            for x in range(cx - rad, cx + rad + 1):
                if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= rr:
                    put(x, y, rgba)

    def stroke_smile(x0, y0, x1, y1, width, rgba):
        # quadratic-ish smile as thick points
        steps = max(size // 2, 24)
        hw = max(1, width // 2)
        for i in range(steps + 1):
            t = i / steps
            # two small arcs side by side (eyes as smiles in the SVG)
            mx = x0 + (x1 - x0) * t
            my = y0 + (y1 - y0) * (4 * t * (1 - t))
            for oy in range(-hw, hw + 1):
                for ox in range(-hw, hw + 1):
                    put(int(mx) + ox, int(my) + oy, rgba)

    # clear
    for i in range(0, len(px), 4):
        px[i : i + 4] = bytes(clear)

    s = size / 64.0
    fill_round_rect(int(6 * s), int(10 * s), int(58 * s), int(52 * s), int(14 * s), green)
    fill_circle(int(17 * s), int(54 * s), max(2, int(5 * s)), white)
    fill_circle(int(47 * s), int(54 * s), max(2, int(5 * s)), white)
    fill_round_rect(int(12 * s), int(16 * s), int(52 * s), int(46 * s), int(10 * s), screen)
    stroke_smile(int(20 * s), int(32 * s), int(28 * s), int(28 * s), max(2, int(3 * s)), white)
    stroke_smile(int(36 * s), int(32 * s), int(44 * s), int(28 * s), max(2, int(3 * s)), white)
    return bytes(px)


def _png(size: int, rgba: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + rgba[y * size * 4 : (y + 1) * size * 4] for y in range(size))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _bmp_bgra(size: int, rgba: bytes) -> bytes:
    # AND mask (1-bit) + XOR BGRA bottom-up for ICO
    row_xor = size * 4
    xor = bytearray(row_xor * size)
    for y in range(size):
        src_y = size - 1 - y
        for x in range(size):
            si = (src_y * size + x) * 4
            di = y * row_xor + x * 4
            r, g, b, a = rgba[si : si + 4]
            xor[di : di + 4] = bytes((b, g, r, a))
    and_row = ((size + 31) // 32) * 4
    and_mask = bytes(and_row * size)
    header = struct.pack(
        "<IIIHHIIIIII",
        40,
        size,
        size * 2,
        1,
        32,
        0,
        len(xor),
        0,
        0,
        0,
        0,
    )
    return header + bytes(xor) + and_mask


def write_ico(path: Path, sizes=(16, 32, 48, 256)) -> None:
    images = []
    for size in sizes:
        rgba = _draw(size)
        images.append((size, _bmp_bgra(size, rgba)))
    count = len(images)
    offset = 6 + 16 * count
    out = bytearray(struct.pack("<HHH", 0, 1, count))
    payloads = b""
    for size, data in images:
        w = 0 if size >= 256 else size
        h = 0 if size >= 256 else size
        out += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset + len(payloads))
        payloads += data
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out) + payloads)


def write_png(path: Path, size: int = 256) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_png(size, _draw(size)))


def write_icns(path: Path) -> None:
    # Modern ICNS entries that store PNG payloads.
    mapping = {
        b"icp4": 16,
        b"icp5": 32,
        b"icp6": 64,
        b"ic07": 128,
        b"ic08": 256,
        b"ic09": 512,
    }
    parts = []
    for tag, size in mapping.items():
        data = _png(size, _draw(size))
        parts.append(tag + struct.pack(">I", 8 + len(data)) + data)
    body = b"".join(parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"icns" + struct.pack(">I", 8 + len(body)) + body)


def main() -> None:
    write_png(STATIC / "icon.png", 256)
    write_ico(STATIC / "icon.ico")
    write_icns(MAC_RES / "AppIcon.icns")
    write_png(MAC_RES / "icon.png", 256)
    print("Wrote:")
    print(" ", STATIC / "icon.png")
    print(" ", STATIC / "icon.ico")
    print(" ", MAC_RES / "AppIcon.icns")


if __name__ == "__main__":
    main()
