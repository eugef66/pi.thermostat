"""Tiny drawing description shared by the diagram scripts: one list of primitives,
rendered to both SVG (always) and PNG (needs Pillow)."""
from xml.sax.saxutils import escape

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"


class Canvas:
    def __init__(self, w, h, bg="#fbfaf6", title=""):
        self.w, self.h, self.bg, self.title, self.prims = w, h, bg, title, []

    def rect(self, x, y, w, h, fill="none", stroke="#333", sw=2, r=10):
        self.prims.append(("rect", x, y, w, h, fill, stroke, sw, r))

    def text(self, x, y, s, size=14, anchor="start", bold=False, fill="#222", italic=False):
        self.prims.append(("text", x, y, s, size, anchor, bold, fill, italic))

    def poly(self, pts, color, sw=3):
        self.prims.append(("poly", pts, color, sw))

    def bez(self, p0, c1, c2, p1, color, sw=3):
        self.prims.append(("bez", p0, c1, c2, p1, color, sw))

    def dot(self, x, y, r=5, fill="#222", ring=None):
        self.prims.append(("dot", x, y, r, fill, ring))

    # ============================================================== SVG renderer
    def svg(self):
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" '
               'font-family="DejaVu Sans, Verdana, Arial, sans-serif">',
               f'<title>{escape(self.title)}</title>']
        for p in self.prims:
            k = p[0]
            if k == "rect":
                _, x, y, w, h, fill, stroke, sw, r = p
                out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
            elif k == "text":
                _, x, y, s, size, anchor, bold, fill, italic = p
                out.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" fill="{fill}"'
                           + (' font-weight="bold"' if bold else '') + (' font-style="italic"' if italic else '')
                           + f'>{escape(s)}</text>')
            elif k == "poly":
                _, pts, col, sw = p
                out.append('<polyline fill="none" stroke-linejoin="round" stroke-linecap="round" '
                           f'stroke="{col}" stroke-width="{sw}" points="{" ".join(f"{x},{y}" for x, y in pts)}"/>')
            elif k == "bez":
                _, a, b, c, d, col, sw = p
                out.append(f'<path fill="none" stroke-linecap="round" stroke="{col}" stroke-width="{sw}" '
                           f'd="M{a[0]},{a[1]} C{b[0]},{b[1]} {c[0]},{c[1]} {d[0]},{d[1]}"/>')
            elif k == "dot":
                _, x, y, r, fill, ring = p
                out.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}"'
                           + (f' stroke="{ring}" stroke-width="3"' if ring else '') + '/>')
        out.append("</svg>")
        return "\n".join(out)


    # ============================================================== PNG renderer
    def png(self, path, scale=2, ss=2):
        from PIL import Image, ImageDraw, ImageFont
        k = scale * ss
        img = Image.new("RGB", (self.w * k, self.h * k), self.bg)
        d = ImageDraw.Draw(img)
        base = FONT_DIR
        fonts = {}

        def font(size, bold, italic):
            key = (size, bold, italic)
            if key not in fonts:
                name = "DejaVuSans" + ("-BoldOblique" if bold and italic else "-Bold" if bold else "-Oblique" if italic else "")
                fonts[key] = ImageFont.truetype(base + name + ".ttf", round(size * k))
            return fonts[key]

        for p in self.prims:
            t = p[0]
            if t == "rect":
                _, x, y, w, h, fill, stroke, sw, r = p
                if stroke == "none" and r == 0:
                    d.rectangle([x * k, y * k, (x + w) * k, (y + h) * k], fill=None if fill == "none" else fill)
                else:
                    d.rounded_rectangle([x * k, y * k, (x + w) * k, (y + h) * k], radius=r * k,
                                        fill=None if fill == "none" else fill,
                                        outline=None if stroke == "none" else stroke, width=max(1, round(sw * k)))
            elif t == "text":
                _, x, y, s, size, anchor, bold, fill, italic = p
                d.text((x * k, y * k), s, font=font(size, bold, italic), fill=fill,
                       anchor={"start": "ls", "middle": "ms", "end": "rs"}[anchor])
            elif t == "poly":
                _, pts, col, sw = p
                d.line([(x * k, y * k) for x, y in pts], fill=col, width=round(sw * k), joint="curve")
            elif t == "bez":
                _, a, b, c, e, col, sw = p
                pts = []
                for i in range(81):
                    u = i / 80
                    pts.append(tuple(((1 - u) ** 3 * a[j] + 3 * (1 - u) ** 2 * u * b[j]
                                      + 3 * (1 - u) * u ** 2 * c[j] + u ** 3 * e[j]) * k for j in range(2)))
                d.line(pts, fill=col, width=round(sw * k), joint="curve")
            elif t == "dot":
                _, x, y, r, fill, ring = p
                d.ellipse([(x - r) * k, (y - r) * k, (x + r) * k, (y + r) * k], fill=fill,
                          outline=ring, width=round(3 * k) if ring else 0)
        img.resize((self.w * scale, self.h * scale), Image.LANCZOS).save(path)


