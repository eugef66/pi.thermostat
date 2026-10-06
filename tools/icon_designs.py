"""App icon: the original thermostat (yellow frame, mint "72" display, red up / blue down
arrows) redrawn in a modern flat style. Three variants. Needs Pillow.
Geometry is in 0..1 units; `scale` < 1 shrinks the artwork toward the centre (maskable)."""
from PIL import Image, ImageDraw, ImageFilter

K = 4                                           # supersampling
YELLOW = ((255, 214, 64), (255, 176, 0))
RED, BLUE, INK = (230, 57, 70), (30, 136, 229), (14, 40, 38)

SEGMENTS = {"7": "abc", "2": "abged"}


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient(n, c0, c1):
    img = Image.new("RGB", (n, n))
    px = img.load()
    for y in range(n):
        for x in range(n):
            px[x, y] = lerp(c0, c1, (x + y) / (2 * (n - 1)))
    return img


def digit_polys(x0, y0, dw, dh, t, digit):
    """Seven-segment LCD digit as hexagonal segment polygons (they meet with a hairline gap)."""
    g, h = t * .14, t / 2
    xl, xr, yt, ym, yb = x0 + h, x0 + dw - h, y0 + h, y0 + dh / 2, y0 + dh - h

    def horiz(yc):
        x1, x2 = xl + g * 1.6, xr - g * 1.6
        return [(x1, yc), (x1 + h, yc - h), (x2 - h, yc - h), (x2, yc), (x2 - h, yc + h), (x1 + h, yc + h)]

    def vert(xc, y1, y2):
        y1, y2 = y1 + g * 1.6, y2 - g * 1.6
        return [(xc, y1), (xc + h, y1 + h), (xc + h, y2 - h), (xc, y2), (xc - h, y2 - h), (xc - h, y1 + h)]

    seg = {"a": horiz(yt), "g": horiz(ym), "d": horiz(yb),
           "f": vert(xl, yt, ym), "b": vert(xr, yt, ym), "e": vert(xl, ym, yb), "c": vert(xr, ym, yb)}
    return [seg[k] for k in SEGMENTS[digit]]


def triangle(cx, cy, w, h, up):
    return [(cx, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)] if up else \
           [(cx, cy + h / 2), (cx + w / 2, cy - h / 2), (cx - w / 2, cy - h / 2)]


class Layer:
    def __init__(self, n, s):
        self.n, self.s = n, s
        self.img = Image.new("RGBA", (n * K, n * K), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def p(self, x, y):
        return ((0.5 + (x - 0.5) * self.s) * self.n * K, (0.5 + (y - 0.5) * self.s) * self.n * K)

    def l(self, v):
        return v * self.s * self.n * K

    def rrect(self, x0, y0, x1, y1, fill, radius):
        a, b = self.p(x0, y0), self.p(x1, y1)
        self.d.rounded_rectangle([a[0], a[1], b[0], b[1]], radius=self.l(radius), fill=fill)

    def line(self, a, b, w, fill):
        pa, pb = self.p(*a), self.p(*b)
        self.d.line([pa, pb], fill=fill, width=round(self.l(w)))

    def rounded_poly(self, pts, fill, r):
        """Polygon with softened corners: fill it, then stroke the edges with round joins."""
        q = [self.p(*pt) for pt in pts]
        self.d.polygon(q, fill=fill)
        w = round(self.l(r) * 2)
        for i in range(len(q)):
            a, b = q[i], q[(i + 1) % len(q)]
            self.d.line([a, b], fill=fill, width=w)
            self.d.ellipse([a[0] - w / 2, a[1] - w / 2, a[0] + w / 2, a[1] + w / 2], fill=fill)

    def digits(self, x0, y0, dw, dh, t, gap, text, fill):
        for i, ch in enumerate(text):
            for poly in digit_polys(x0 + i * (dw + gap), y0, dw, dh, t, ch):
                self.rounded_poly(poly, fill, t * .09)

    def out(self):
        return self.img.resize((self.n, self.n), Image.LANCZOS)


def grad_shape(n, s, draw, c0, c1):
    """Fill the shape drawn by draw(layer) with a diagonal gradient."""
    lay = Layer(n, s)
    draw(lay)
    mask = lay.out().split()[3]
    out = gradient(n, c0, c1).convert("RGBA")
    out.putalpha(mask)
    return out


def soft(n, s, draw, dy=.014, blur=.012, alpha=70):
    lay = Layer(n, s)
    draw(lay, dy)
    layer = lay.out()
    shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    shadow.putalpha(layer.split()[3].point(lambda v: v * alpha // 255))
    return shadow.filter(ImageFilter.GaussianBlur(n * blur))


def arrows(lay, cx, up_y, down_y, w=.115, h=.10, r=.012):
    lay.rounded_poly(triangle(cx, up_y, w, h, True), RED, r)
    lay.rounded_poly(triangle(cx, down_y, w, h, False), BLUE, r)


PANEL = (.08, .20, .66, .80)
PILL = (.71, .20, .92, .80)


def design_1(n, s=1.0):
    """Classic: yellow tile, mint display, white arrow pill."""
    base = gradient(n, *YELLOW).convert("RGBA")
    base.alpha_composite(soft(n, s, lambda L, dy: (
        L.rrect(PANEL[0], PANEL[1] + dy, PANEL[2], PANEL[3] + dy, (0, 0, 0, 255), .09),
        L.rrect(PILL[0], PILL[1] + dy, PILL[2], PILL[3] + dy, (0, 0, 0, 255), .105))))
    base.alpha_composite(grad_shape(n, s, lambda L: L.rrect(*PANEL, (255, 255, 255, 255), .09),
                                    (120, 245, 182), (0, 196, 148)))
    top = Layer(n, s)
    top.digits(.13, .30, .21, .40, .05, .06, "72", INK)
    top.rrect(*PILL, (255, 255, 255, 255), .105)
    top.line((.75, .5), (.88, .5), .008, (216, 222, 228, 255))
    arrows(top, .815, .355, .645)
    base.alpha_composite(top.out())
    return base


def design_2(n, s=1.0):
    """Night display: dark panel with glowing mint digits."""
    base = gradient(n, *YELLOW).convert("RGBA")
    base.alpha_composite(soft(n, s, lambda L, dy: (
        L.rrect(PANEL[0], PANEL[1] + dy, PANEL[2], PANEL[3] + dy, (0, 0, 0, 255), .09),
        L.rrect(PILL[0], PILL[1] + dy, PILL[2], PILL[3] + dy, (0, 0, 0, 255), .105))))
    base.alpha_composite(grad_shape(n, s, lambda L: L.rrect(*PANEL, (255, 255, 255, 255), .09),
                                    (24, 60, 78), (9, 26, 38)))
    glow = Layer(n, s)
    glow.digits(.13, .30, .21, .40, .05, .06, "72", (110, 255, 200, 255))
    base.alpha_composite(glow.out().filter(ImageFilter.GaussianBlur(n * .018)))
    base.alpha_composite(glow.out())
    top = Layer(n, s)
    top.rrect(*PILL, (255, 255, 255, 255), .105)
    top.line((.75, .5), (.88, .5), .008, (216, 222, 228, 255))
    arrows(top, .815, .355, .645)
    base.alpha_composite(top.out())
    return base


def design_3(n, s=1.0):
    """Simple and bold, for small sizes: one mint tile in a yellow frame, big digits, arrows."""
    base = gradient(n, *YELLOW).convert("RGBA")
    base.alpha_composite(grad_shape(n, s, lambda L: L.rrect(.075, .075, .925, .925, (255, 255, 255, 255), .12),
                                    (120, 245, 182), (0, 190, 140)))
    top = Layer(n, s)
    top.digits(.11, .25, .24, .50, .065, .07, "72", INK)
    arrows(top, .815, .36, .64, w=.15, h=.13, r=.016)
    base.alpha_composite(top.out())
    return base


DESIGNS = {"1": ("Classic", design_1), "2": ("Night display", design_2), "3": ("Bold & simple", design_3)}
