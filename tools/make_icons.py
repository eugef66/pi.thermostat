"""Regenerates static/icons/* from tools/icon_designs.py (needs Pillow).
    python3 tools/make_icons.py              # default design 1
    python3 tools/make_icons.py --design 2   # 1 classic, 2 night display, 3 bold & simple
The 32 px favicon always uses design 3, the one that stays legible when tiny."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw
import icon_designs as D

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "icons")


def rounded(img, frac=.22):
    n = img.size[0]
    m = Image.new("L", (n * 4, n * 4), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, n * 4 - 1, n * 4 - 1], radius=n * 4 * frac, fill=255)
    img = img.copy()
    img.putalpha(m.resize((n, n), Image.LANCZOS))
    return img


def svg_design_1() -> str:
    """Vector twin of design 1 (same geometry as the PNGs)."""
    def pts(poly):
        return " ".join(f"{x * 512:.1f},{y * 512:.1f}" for x, y in poly)

    def rr(box, r, fill, extra=""):
        x0, y0, x1, y1 = box
        return (f'<rect x="{x0 * 512:.1f}" y="{y0 * 512:.1f}" width="{(x1 - x0) * 512:.1f}" '
                f'height="{(y1 - y0) * 512:.1f}" rx="{r * 512:.1f}" fill="{fill}" {extra}/>')

    digits = "".join(
        f'<polygon points="{pts(p)}"/>'
        for i, ch in enumerate("72") for p in D.digit_polys(.13 + i * .27, .30, .21, .40, .05, ch))
    tri = lambda up, col, cy: (f'<polygon points="{pts(D.triangle(.815, cy, .115, .10, up))}" fill="{col}" '
                               f'stroke="{col}" stroke-width="{.024 * 512:.1f}" stroke-linejoin="round"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="y" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffd640"/><stop offset="1" stop-color="#ffb000"/></linearGradient>
    <linearGradient id="m" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#78f5b6"/><stop offset="1" stop-color="#00c494"/></linearGradient>
    <filter id="s" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="7" stdDeviation="6" flood-opacity=".28"/></filter>
  </defs>
  <rect width="512" height="512" rx="113" fill="url(#y)"/>
  <g filter="url(#s)">{rr(D_PANEL, .09, "url(#m)")}{rr(D_PILL, .105, "#fff")}</g>
  <g fill="#0e2826" stroke="#0e2826" stroke-width="{.0045 * 512 * 2:.1f}" stroke-linejoin="round">{digits}</g>
  <line x1="{.75 * 512}" y1="256" x2="{.88 * 512}" y2="256" stroke="#d8dee4" stroke-width="4"/>
  {tri(True, "#e63946", .355)}{tri(False, "#1e88e5", .645)}
</svg>
'''


D_PANEL, D_PILL = D.PANEL, D.PILL

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", default="1", choices=sorted(D.DESIGNS))
    a = ap.parse_args()
    design = D.DESIGNS[a.design][1]
    os.makedirs(OUT, exist_ok=True)
    rounded(design(192)).save(os.path.join(OUT, "icon-192.png"))
    rounded(design(512)).save(os.path.join(OUT, "icon-512.png"))
    design(512, 0.8).save(os.path.join(OUT, "icon-maskable-512.png"))        # full bleed, art in the safe zone
    design(180).convert("RGB").save(os.path.join(OUT, "apple-touch-icon-180.png"))   # iOS rounds it itself
    rounded(D.design_3(32)).save(os.path.join(OUT, "favicon-32.png"))
    with open(os.path.join(OUT, "icon.svg"), "w") as f:
        f.write(svg_design_1())
    print(f"wrote icons from design {a.design} ({D.DESIGNS[a.design][0]})")
