#!/usr/bin/env python3
"""Render the WhatsApp bridge's terminal QR code as a PNG image.

The Go bridge prints a half-block Unicode QR code to stdout the first time a
pairing QR arrives. This helper parses that art from a captured log file and
re-emits it as a scannable PNG so it can be opened in an image viewer.

Usage:
    python3 render-bridge-qr.py <log-file> --out PNG [--scale N] [--watch]
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
import time
import zlib
from pathlib import Path

# Half-block characters -> (top module black, bottom module black)
CHARS = {
    " ": (True, True),
    "\u2584": (True, False),  # lower half block
    "\u2580": (False, True),  # upper half block
    "\u2588": (False, False),  # full block
}
BLANK = "\u2588"


ANCHOR = "Scan this QR code with your WhatsApp app:"
END = "Waiting for QR code scan"


def _is_art(line: str) -> bool:
    return bool(line) and len(line) >= 21 and all(ch in CHARS for ch in line)


def _clean(block: list[str]) -> list[str]:
    # qrterminal frames the code with a trailing half-block border line whose
    # bottom half is black; drop it so the quiet zone stays white.
    while block and set(block[-1]) == {"\u2580"}:
        block.pop()
    return block


def find_blocks(text: str) -> list[list[str]]:
    """Return QR art blocks found in the log text."""
    lines = text.splitlines()
    blocks: list[list[str]] = []
    i = 0
    while i < len(lines):
        if ANCHOR in lines[i]:
            art: list[str] = []
            i += 1
            while i < len(lines) and END not in lines[i]:
                if _is_art(lines[i]):
                    art.append(lines[i])
                i += 1
            if len(art) >= 10:
                blocks.append(_clean(art))
            continue
        i += 1

    if blocks:
        return blocks

    # Fallback: group consecutive art lines (for logs without the banner).
    current: list[str] = []
    for line in lines:
        if _is_art(line):
            current.append(line)
        else:
            if len(current) >= 10:
                blocks.append(_clean(current))
            current = []
    if len(current) >= 10:
        blocks.append(_clean(current))
    return blocks


def to_bitmap(block: list[str]) -> list[list[bool]]:
    """Expand the half-block art into a module grid (True = black)."""
    width = max(len(line) for line in block)
    rows: list[list[bool]] = []
    for line in block:
        top: list[bool] = []
        bottom: list[bool] = []
        for ch in line.ljust(width, BLANK):
            t, b = CHARS[ch]
            top.append(t)
            bottom.append(b)
        rows.append(top)
        rows.append(bottom)
    return rows


def write_png(rows: list[list[bool]], scale: int, out: Path) -> None:
    """Write the module grid as a grayscale PNG (no third-party deps)."""
    margin = 4
    width = len(rows[0]) + margin * 2
    height = len(rows) + margin * 2
    raw = bytearray()
    for r in range(height):
        row = bytearray()
        for c in range(width):
            inside = margin <= r < height - margin and margin <= c < width - margin
            black = rows[r - margin][c - margin] if inside else False
            row += bytes([0 if black else 255]) * scale
        for _ in range(scale):
            raw.append(0)  # PNG filter type 0
            raw += row

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width * scale, height * scale, 8, 0, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(out, flags, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(png)
        os.fchmod(output.fileno(), 0o600)


def render(log_path: Path, out: Path, scale: int, index: int) -> bool:
    text = log_path.read_text(encoding="utf-8", errors="replace")
    blocks = find_blocks(text)
    if len(blocks) <= index:
        return False
    write_png(to_bitmap(blocks[index]), scale, out)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="bridge log file to parse")
    parser.add_argument("--out", type=Path, required=True, help="private path for the rendered PNG")
    parser.add_argument("--scale", type=int, default=12, help="pixels per QR module")
    parser.add_argument("--index", type=int, default=-1, help="which QR block to render (-1 = newest)")
    parser.add_argument("--watch", action="store_true", help="keep rendering new QR blocks")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    if not args.watch:
        index = args.index if args.index >= 0 else -1
        if index == -1:
            text = args.log.read_text(encoding="utf-8", errors="replace")
            count = len(find_blocks(text))
            index = count - 1
        if index < 0 or not render(args.log, args.out, args.scale, index):
            print(f"no QR block found in {args.log}", file=sys.stderr)
            return 1
        print(args.out)
        return 0

    seen = 0
    while True:
        if render(args.log, args.out, args.scale, seen):
            seen += 1
            print(f"rendered QR #{seen} -> {args.out}", flush=True)
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
