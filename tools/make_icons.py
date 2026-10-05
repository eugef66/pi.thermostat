"""Regenerates static/icons/*.png from the same design as icon.svg (needs Pillow).
Design: orange-purple-blue diagonal gradient, white dial ring, needle and hub."""
import math
import os
from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(__file__), "..", "static", "icons")
STOPS = [(0.0, (247, 103, 7)), (0.5, (156, 54, 181)), (1.0, (28, 126, 214))]  # orange, purple, blue


def gradient(n):
    img = Image.new("RGB", (n, n))
    px = img.load()
    for y in range(n):
        for x in range(n):
            t = (x + y) / (2 * (n - 1))
            (t0, c0), (t1, c1) = (STOPS[0], STOPS[1]) if t < 0.5 else (STOPS[1], STOPS[2])
            u = (t - t0) / (t1 - t0)
            px[x, y] = tuple(round(c0[i] + (c1[i] - c0[i]) * u) for i in range(3))
    return img


def artwork(n, scale):
    """White dial drawn at 4x then downsampled. `scale` shrinks it (maskable safe zone)."""
    k = 4
    big = Image.new("RGBA", (n * k, n * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    c = n * k / 2
    r = n * k * 0.34 * scale
    d.ellipse([c - r, c - r, c + r, c + r], outline="white", width=round(n * k * 0.055 * scale))
    ang = math.radians(-50)                      # needle pointing up-right
    L = r * 0.58
    tip = (c + L * math.sin(-ang), c - L * math.cos(-ang))
    w = round(n * k * 0.05 * scale)
    d.line([(c, c), tip], fill="white", width=w)
    for p in (tip, (c, c)):
        d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill="white")
    h = n * k * 0.05 * scale
    d.ellipse([c - h, c - h, c + h, c + h], fill="white")
    return big.resize((n, n), Image.LANCZOS)


def icon(n, maskable=False, rounded=False):
    img = gradient(n).convert("RGBA")
    img.alpha_composite(artwork(n, 0.8 if maskable else 1.0))
    if rounded:
        mask = Image.new("L", (n * 4, n * 4), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, n * 4 - 1, n * 4 - 1], radius=n * 4 * 0.22, fill=255)
        img.putalpha(mask.resize((n, n), Image.LANCZOS))
    return img


os.makedirs(OUT, exist_ok=True)
icon(192, rounded=True).save(os.path.join(OUT, "icon-192.png"))
icon(512, rounded=True).save(os.path.join(OUT, "icon-512.png"))
icon(512, maskable=True).save(os.path.join(OUT, "icon-maskable-512.png"))
icon(180).convert("RGB").save(os.path.join(OUT, "apple-touch-icon-180.png"))   # iOS rounds it itself
icon(32, rounded=True).save(os.path.join(OUT, "favicon-32.png"))
