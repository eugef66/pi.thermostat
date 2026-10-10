"""Contact sheet of the icon variants at large and home-screen sizes -> docs/icon-options.png"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw, ImageFont
import icon_designs as D

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "icon-options.png")


def rounded(img, frac=.22):
    n = img.size[0]
    m = Image.new("L", (n * 4, n * 4), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, n * 4 - 1, n * 4 - 1], radius=n * 4 * frac, fill=255)
    img = img.copy()
    img.putalpha(m.resize((n, n), Image.LANCZOS))
    return img


def font(size, bold=False):
    return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else ""), size)


W, H = 1260, 640
sheet = Image.new("RGB", (W, H), "#f4f1ea")
d = ImageDraw.Draw(sheet)
d.text((W // 2, 34), "Thermostat icon options", font=font(28, True), fill="#1f2933", anchor="mm")
big, gap = 300, 90
for i, (k, (name, fn)) in enumerate(D.DESIGNS.items()):
    x = gap + i * (big + gap)
    ic = rounded(fn(512)).resize((big, big), Image.LANCZOS)
    sheet.paste(ic, (x, 80), ic)
    d.text((x + big // 2, 415), k, font=font(34, True), fill="#1f2933", anchor="mm")
    d.text((x + big // 2, 452), name, font=font(17), fill="#5f6b76", anchor="mm")
    for j, sz in enumerate((76, 60, 40, 29)):
        sm = rounded(fn(256)).resize((sz, sz), Image.LANCZOS)
        sheet.paste(sm, (x + 6 + j * 86, 490), sm)
    d.text((x + big // 2, 590), "as on a home screen / browser tab", font=font(12), fill="#8a949e", anchor="mm")
sheet.save(OUT)
print("wrote docs/icon-options.png")
