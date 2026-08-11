"""Generate block-style extension icons (16/48/128) using only the stdlib.

Draws a red circle outline with a diagonal slash onto a transparent RGBA PNG.
Rasterization is done with a simple per-pixel distance test (no anti-aliasing
needed at these sizes), then encoded as PNG via zlib.
"""
import os
import struct
import zlib

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "icons")
RED = (244, 33, 46, 255)
TRANSPARENT = (0, 0, 0, 0)


def dist_to_segment(px, py, ax, ay, bx, by):
    """Distance from point (px,py) to segment (ax,ay)-(bx,by)."""
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def draw_icon(size: int):
    pixels = [[TRANSPARENT] * size for _ in range(size)]
    cx = cy = (size - 1) / 2.0
    radius = size / 2.0 - max(int(round(size * 0.10)), 1) - 0.5
    thickness = max(int(round(size * 0.10)), 1)
    half = thickness / 2.0

    # Line endpoints (diagonal slash from bottom-left to top-right inside circle)
    k = 0.28  # offset toward center along the radius
    ax = cx - radius * (1 - k)
    ay = cy + radius * (1 - k)
    bx = cx + radius * (1 - k)
    by = cy - radius * (1 - k)

    for y in range(size):
        for x in range(size):
            on_circle = abs(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 - radius) <= half
            on_slash = dist_to_segment(x + 0.5, y + 0.5, ax, ay, bx, by) <= half
            if on_circle or on_slash:
                pixels[y][x] = RED
    return pixels


def write_png(path: str, pixels) -> None:
    height = len(pixels)
    width = len(pixels[0])

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = bytearray()
    for row in pixels:
        raw.append(0)  # filter type 0 (None)
        for (r, g, b, a) in row:
            raw.extend((r, g, b, a))
    compressed = zlib.compress(bytes(raw), 9)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", compressed)
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    for s in (16, 48, 128):
        path = os.path.join(OUT_DIR, f"icon{s}.png")
        write_png(path, draw_icon(s))
        print("wrote", path)


if __name__ == "__main__":
    main()
