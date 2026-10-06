"""Draws docs/wiring.svg and docs/wiring.png. Run: python3 tools/make_wiring_diagram.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drawlib import Canvas

W, H = 1200, 980
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")
C = Canvas(W, H, title="pi.thermostat wiring diagram")
rect, text, poly, bez, dot = C.rect, C.text, C.poly, C.bez, C.dot


# ---------------------------------------------------------------- title
rect(0, 0, W, H, fill="#fbfaf6", stroke="none", sw=0, r=0)
text(600, 38, "pi.thermostat wiring", 26, "middle", True)
text(600, 62, "Raspberry Pi 3B  \u2192  4-channel relay board  \u2192  furnace / AC control board (24 VAC, low voltage)", 14, "middle", fill="#555")
text(150, 92, "RASPBERRY PI 3B", 13, "middle", True, "#777")
text(750, 92, "SENSOR + RELAY BOARD", 13, "middle", True, "#777")
text(1095, 92, "FURNACE / AC", 13, "middle", True, "#777")

# ------------------------------------------------------------- Pi header
rect(30, 105, 240, 650, fill="#e7f5e9", stroke="#2b8a3e")
text(150, 128, "40-pin header (used pins only)", 12, "middle", fill="#2b6a3a")
pins = [  # (physical pin, label, colour, destination key)
    (1,  "3V3",        "#e8590c", "dht+"),
    (2,  "5V",         "#c92a2a", "jd"),
    (3,  "GPIO 2",     "#1c7ed6", "in1"),
    (5,  "GPIO 3",     "#1098ad", "in2"),
    (6,  "GND",        "#343a40", "dht-"),
    (7,  "GPIO 4",     "#2f9e44", "dhtout"),
    (9,  "GND",        "#343a40", "gnd"),
    (17, "3V3",        "#f08c00", "vcc"),
    (29, "GPIO 5",     "#7048e8", "in3"),
    (31, "GPIO 6",     "#c2255c", "in4"),
]
py = {}
for i, (pin, lab, col, key) in enumerate(pins):
    y = 160 + i * 58
    py[key] = (270, y)
    text(48, y + 5, f"Pin {pin}", 14, bold=True)
    text(112, y + 5, lab, 14, fill="#444")
    dot(270, y, 6, col)

# ------------------------------------------------------------ DHT22 block
rect(640, 105, 220, 180, fill="#fff", stroke="#555")
text(750, 130, "DHT22 / AM2302", 15, "middle", True)
text(750, 270, "3-pin board, pull-up built in", 12, "middle", fill="#777")
dht = {"dht+": ("+", 170), "dhtout": ("out", 210), "dht-": ("\u2212", 250)}
tp = {}
for k, (lab, y) in dht.items():
    tp[k] = (640, y)
    dot(640, y, 6, "#555")
    text(656, y + 5, lab, 15, bold=True)

# ----------------------------------------------------------- relay block
rect(640, 330, 240, 490, fill="#fff", stroke="#555")
text(760, 354, "4-channel relay board", 15, "middle", True)
left = {"jd": ("JD-VCC", 392), "vcc": ("VCC", 432), "gnd": ("GND", 472),
        "in1": ("IN1", 540), "in2": ("IN2", 620), "in3": ("IN3", 700), "in4": ("IN4", 780)}
for k, (lab, y) in left.items():
    tp[k] = (640, y)
    dot(640, y, 6, "#555")
    text(656, y + 5, lab, 14, bold=True)
text(752, 432, "yellow jumper", 11, fill="#a61e1e", italic=True)
text(752, 446, "REMOVED", 11, fill="#a61e1e", italic=True, bold=True)
rows = [("K1", 540, "W1"), ("K2", 620, "Y"), ("K3", 700, "W2"), ("K4", 780, "G")]
for k, y, _ in rows:
    text(765, y + 5, k, 15, "middle", True, "#555")
    text(872, y - 10, "COM", 11, "end", fill="#555")
    text(872, y + 22, "NO", 11, "end", fill="#555")
    dot(880, y - 14, 5, "#555"); dot(880, y + 14, 5, "#555")

# ---------------------------------------------------- equipment terminals
rect(1010, 420, 170, 450, fill="#fff", stroke="#555")
text(1095, 444, "Furnace / AC", 14, "middle", True)
text(1095, 462, "control board", 14, "middle", True)
eq = [("R", 500, "#c92a2a"), ("W1", 540, "#495057"), ("Y", 620, "#e0a800"),
      ("W2", 700, "#868e96"), ("G", 780, "#2f9e44")]
for lab, y, col in eq:
    dot(1010, y, 6, col)
    text(1026, y + 5, lab, 15, bold=True)
dot(1010, 840, 6, "#bbb")
text(1026, 845, "C  (not used)", 13, fill="#888")

# ----------------------------------------------------------- Pi -> boards
for pin, lab, col, key in pins:
    (x0, y0), (x1, y1) = py[key], tp[key]
    bez((x0, y0), (x0 + 190, y0), (x1 - 190, y1), (x1, y1), col, 3)

# ------------------------------------------------- relays -> equipment
BUS = 905
poly([(880, 540 - 14), (BUS, 540 - 14), (BUS, 500), (1010, 500)], "#c92a2a", 4)         # R bus
for k, y, name in rows[1:]:
    poly([(880, y - 14), (BUS, y - 14)], "#c92a2a", 4)
    dot(BUS, y - 14, 5, "#c92a2a")
dot(BUS, 540 - 14, 5, "#c92a2a")
poly([(BUS, 526), (BUS, 766)], "#c92a2a", 4)
for (k, y, name), (lab, ey, col) in zip(rows, eq[1:]):
    poly([(880, y + 14), (945, y + 14), (945, ey), (1010, ey)], col, 4)
text(BUS - 8, 498, "R (24 VAC) to every COM", 11, "end", fill="#c92a2a", bold=True)

# ------------------------------------------------------------------ notes
rect(30, 870, 560, 90, fill="#fff8e1", stroke="#e0a800", sw=1.5)
notes = [
    "Switch the furnace/AC OFF at the breaker before touching any wire.",
    "Connect ONE controller to W1/W2/Y/G: disconnect the smart thermostat.",
    "Use NO, never NC: if the Pi loses power the equipment stops calling.",
    "Crossing lines are not connected unless there is a dot.",
]
for i, n in enumerate(notes):
    text(44, 893 + i * 20, "\u2022 " + n, 12.5)
text(1180, 960, "Wire colours are conventions; yours may differ.", 11, "end", fill="#888", italic=True)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "wiring.svg"), "w") as f:
        f.write(C.svg())
    C.png(os.path.join(OUT, "wiring.png"))
    print("wrote docs/wiring.svg and docs/wiring.png")
