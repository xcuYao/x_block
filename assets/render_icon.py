"""Rasterize the X Block store icon following Chrome Web Store spec.

- Canvas 128x128, actual artwork 96x96, 16px transparent padding each side.
- Dark body -> faint outer white halo for visibility on dark backgrounds.
- Pure stdlib (zlib), no third-party deps. 4x supersampling + box AA.
"""
import os
import struct
import zlib

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "icons")
STORE_OUT = os.path.join(os.path.dirname(__file__), "store-icon-1024.png")

SS = 4          # supersampling factor (kept modest for speed)
SIZE = 128
CONTENT = 96
PAD = (SIZE - CONTENT) // 2

BLACK = (0, 0, 0, 255)
WHITE = (255, 255, 255, 255)
RED = (244, 33, 46, 255)
TRANSPARENT = (0, 0, 0, 0)


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def rounded_rect_sdf(x, y, x0, y0, x1, y1, r):
    """Signed distance to a rounded rectangle; negative inside."""
    qx = abs((x - x0) - (x1 - x0) / 2.0) - ((x1 - x0) / 2.0 - r)
    qy = abs((y - y0) - (y1 - y0) / 2.0) - ((y1 - y0) / 2.0 - r)
    ox = max(qx, 0.0)
    oy = max(qy, 0.0)
    outside = (ox * ox + oy * oy) ** 0.5
    inside = min(max(qx, qy), 0.0)
    return outside + inside - r


def point_in_poly(px, py, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def poly_coverage(poly, x, y):
    samples = [
        (x - 0.3, y - 0.3), (x + 0.3, y - 0.3),
        (x - 0.3, y + 0.3), (x + 0.3, y + 0.3),
        (x, y),
    ]
    c = 0
    for sx, sy in samples:
        if point_in_poly(sx, sy, poly):
            c += 1
    return c / len(samples)


def make_icon(size=SIZE):
    big = size * SS
    inv = SIZE / big  # canvas units per subpixel

    # Geometry in canvas units
    x0, y0 = float(PAD), float(PAD)
    x1, y1 = float(SIZE - PAD), float(SIZE - PAD)
    rr = 22.0
    cx = cy = SIZE / 2.0
    radius = 42.0
    thickness = 6.5
    half = thickness / 2.0
    line = (34.3, 93.7, 93.7, 34.3)

    # X glyph polygons in canvas units (translate 36,36 scale 2.333 of 24-unit path)
    tx, ty, ts = 36.0, 36.0, 2.333

    def X(v):
        return tx + v * ts

    def Y(v):
        return ty + v * ts

    x_outer = [
        (X(18.244), Y(2.25)), (X(21.552), Y(2.25)),
        (X(14.325), Y(10.51)), (X(22.827), Y(21.75)),
        (X(16.17), Y(21.75)), (X(10.956), Y(14.933)),
        (X(4.99), Y(21.75)), (X(1.68), Y(21.75)),
        (X(9.41), Y(12.915)), (X(1.254), Y(2.25)),
        (X(8.08), Y(2.25)), (X(13.12), Y(8.481)),
    ]
    x_hole = [
        (X(8.0), Y(7.0)), (X(9.7), Y(7.0)),
        (X(17.0), Y(17.0)), (X(15.3), Y(17.0)),
    ]

    # Single buffer: list of rows, each row list of (r,g,b,a)
    buf = [[TRANSPARENT] * big for _ in range(big)]

    def composite(bx, by, color, cov):
        if cov <= 0.0:
            return
        dr, dg, db, da = color
        sr, sg, sb, sa = buf[by][bx]
        fa = cov * da / 255.0
        ba = sa / 255.0
        out_a = fa + ba * (1.0 - fa)
        if out_a <= 0.0:
            return
        nr = (dr * fa + sr * ba * (1.0 - fa)) / out_a
        ng = (dg * fa + sg * ba * (1.0 - fa)) / out_a
        nb = (db * fa + sb * ba * (1.0 - fa)) / out_a
        buf[by][bx] = (int(nr), int(ng), int(nb), int(out_a * 255))

    # Precompute black body coverage per subpixel (one pass), used for body + halo.
    # Store as byte-like 0..255 alpha to avoid recomputing SDF.
    body_alpha = bytearray(big * big)
    for by in range(big):
        cy_u = (by + 0.5) * inv
        row_base = by * big
        for bx in range(big):
            cx_u = (bx + 0.5) * inv
            d = rounded_rect_sdf(cx_u, cy_u, x0, y0, x1, y1, rr)
            if d <= -0.75:
                a = 255
            elif d >= 0.75:
                a = 0
            else:
                a = int(clamp((0.75 - d) / 1.5) * 255)
            body_alpha[row_base + bx] = a

    # Halo: a very faint white ring just outside the body, computed directly
    # from the rounded-rect SDF (no expensive dilation search).
    halo_outer = 2.0   # canvas units outside body
    halo_inner = 0.0
    for by in range(big):
        cy_u = (by + 0.5) * inv
        base = by * big
        for bx in range(big):
            if body_alpha[base + bx] != 0:
                continue  # inside body, halo goes outside
            cx_u = (bx + 0.5) * inv
            d = rounded_rect_sdf(cx_u, cy_u, x0, y0, x1, y1, rr)
            if halo_inner <= d <= halo_outer:
                cov = clamp(1.0 - (d - halo_inner) / (halo_outer - halo_inner))
                composite(bx, by, (255, 255, 255, int(40 * cov)), 1.0)

    # Black body
    for by in range(big):
        base = by * big
        for bx in range(big):
            a = body_alpha[base + bx]
            if a:
                composite(bx, by, BLACK, a / 255.0)

    # White X glyph (outer minus hole)
    for by in range(big):
        cy_u = (by + 0.5) * inv
        for bx in range(big):
            cx_u = (bx + 0.5) * inv
            outer = poly_coverage(x_outer, cx_u, cy_u)
            if outer <= 0.0:
                continue
            inner = poly_coverage(x_hole, cx_u, cy_u)
            cov = clamp(outer - inner)
            composite(bx, by, WHITE, cov)

    # Red circle
    for by in range(big):
        cy_u = (by + 0.5) * inv
        for bx in range(big):
            cx_u = (bx + 0.5) * inv
            d = ((cx_u - cx) ** 2 + (cy_u - cy) ** 2) ** 0.5
            diff = abs(d - radius)
            if diff <= half - 0.5:
                cov = 1.0
            elif diff >= half + 0.5:
                cov = 0.0
            else:
                cov = clamp((half + 0.5 - diff) / 1.0)
            composite(bx, by, RED, cov)

    # Red slash segment
    ax, ay, bx2, by2 = line
    dx = bx2 - ax
    dy = by2 - ay
    seg_len2 = dx * dx + dy * dy
    for by in range(big):
        py = (by + 0.5) * inv
        for bx in range(big):
            px = (bx + 0.5) * inv
            t = ((px - ax) * dx + (py - ay) * dy) / seg_len2
            t = clamp(t)
            qx = ax + t * dx
            qy = ay + t * dy
            d = ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5
            if d <= half - 0.5:
                cov = 1.0
            elif d >= half + 0.5:
                cov = 0.0
            else:
                cov = clamp((half + 0.5 - d) / 1.0)
            composite(bx, by, RED, cov)

    # Downsample with box average
    out = [[TRANSPARENT] * size for _ in range(size)]
    for y in range(size):
        for x in range(size):
            ar = ag = ab = aa = 0.0
            for sy in range(SS):
                row = buf[y * SS + sy]
                for sx in range(SS):
                    r, g, b, a = row[x * SS + sx]
                    ar += r; ag += g; ab += b; aa += a
            n = SS * SS
            out[y][x] = (int(ar / n), int(ag / n), int(ab / n), int(aa / n))
    return out


def write_png(path, pixels):
    height = len(pixels)
    width = len(pixels[0])

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for (r, g, b, a) in row:
            raw.extend((r, g, b, a))
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for s in (16, 48, 128):
        path = os.path.join(OUT_DIR, f"icon{s}.png")
        write_png(path, make_icon(s))
        print("wrote", path)
    write_png(STORE_OUT, make_icon(512))
    print("wrote", STORE_OUT)


if __name__ == "__main__":
    main()
