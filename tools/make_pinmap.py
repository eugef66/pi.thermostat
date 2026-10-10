"""Draws docs/gpio-pinmap.svg and .png: Raspberry Pi 3B 40-pin header with the
pins pi.thermostat uses highlighted. Run: python3 tools/make_pinmap.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drawlib import Canvas

W, H = 1100, 1370
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")
C = Canvas(W, H, title="Raspberry Pi 3B GPIO pin map for pi.thermostat")
rect, text, dot = C.rect, C.text, C.dot

# (physical pin, kind, label) ; kind: 3v3 5v gnd gpio id.   BCM number is in the label.
HEADER = {
    1: ("3v3", "3V3"), 2: ("5v", "5V"),
    3: ("gpio", "GPIO 2 \u00b7 SDA1"), 4: ("5v", "5V"),
    5: ("gpio", "GPIO 3 \u00b7 SCL1"), 6: ("gnd", "GND"),
    7: ("gpio", "GPIO 4"), 8: ("gpio", "GPIO 14 \u00b7 TXD"),
    9: ("gnd", "GND"), 10: ("gpio", "GPIO 15 \u00b7 RXD"),
    11: ("gpio", "GPIO 17"), 12: ("gpio", "GPIO 18 \u00b7 PCM"),
    13: ("gpio", "GPIO 27"), 14: ("gnd", "GND"),
    15: ("gpio", "GPIO 22"), 16: ("gpio", "GPIO 23"),
    17: ("3v3", "3V3"), 18: ("gpio", "GPIO 24"),
    19: ("gpio", "GPIO 10 \u00b7 MOSI"), 20: ("gnd", "GND"),
    21: ("gpio", "GPIO 9 \u00b7 MISO"), 22: ("gpio", "GPIO 25"),
    23: ("gpio", "GPIO 11 \u00b7 SCLK"), 24: ("gpio", "GPIO 8 \u00b7 CE0"),
    25: ("gnd", "GND"), 26: ("gpio", "GPIO 7 \u00b7 CE1"),
    27: ("id", "GPIO 0 \u00b7 ID_SD"), 28: ("id", "GPIO 1 \u00b7 ID_SC"),
    29: ("gpio", "GPIO 5"), 30: ("gnd", "GND"),
    31: ("gpio", "GPIO 6"), 32: ("gpio", "GPIO 12 \u00b7 PWM0"),
    33: ("gpio", "GPIO 13 \u00b7 PWM1"), 34: ("gnd", "GND"),
    35: ("gpio", "GPIO 19 \u00b7 PCM"), 36: ("gpio", "GPIO 16"),
    37: ("gpio", "GPIO 26"), 38: ("gpio", "GPIO 20 \u00b7 PCM"),
    39: ("gnd", "GND"), 40: ("gpio", "GPIO 21 \u00b7 PCM"),
}
FILL = {"3v3": "#f08c00", "5v": "#c92a2a", "gnd": "#343a40", "gpio": "#ced4da", "id": "#ffa8a8"}
# pins pi.thermostat uses: pin -> (colour, text)  (colours match docs/wiring.png)
USED = {
    1: ("#e8590c", "DHT22  +"),            2: ("#c92a2a", "Relay JD-VCC (coil 5V)"),
    3: ("#1c7ed6", "Relay IN1 \u2192 W1 heat"), 5: ("#1098ad", "Relay IN2 \u2192 Y cool"),
    6: ("#343a40", "DHT22  \u2212"),       7: ("#2f9e44", "DHT22  out (data)"),
    9: ("#343a40", "Relay GND"),           17: ("#f08c00", "Relay VCC (logic 3.3V)"),
    29: ("#7048e8", "Relay IN3 \u2192 W2 heat 2"), 31: ("#c2255c", "Relay IN4 \u2192 G fan"),
}
CX_ODD, CX_EVEN, Y0, DY = 520, 580, 175, 46

rect(0, 0, W, H, fill="#fbfaf6", stroke="none", sw=0, r=0)
text(550, 40, "Raspberry Pi 3B \u2014 40-pin GPIO header", 26, "middle", True)
text(550, 64, "Pin = physical position on the header.  GPIO n = the BCM number you put in config.toml.", 14, "middle", fill="#555")
text(550, 86, "Highlighted rows are the pins pi.thermostat uses.", 14, "middle", fill="#555")

# row stripes first, then the header body on top of them
for i in range(20):
    y = Y0 + i * DY
    if i % 2 == 0:
        rect(40, y - 21, 1020, 42, fill="#f1eee6", stroke="none", sw=0, r=0)
rect(480, Y0 - 34, 140, 20 * DY + 12, fill="#2b2f36", stroke="#111", sw=2, r=14)
text(CX_ODD, Y0 - 44, "odd", 12, "middle", fill="#777")
text(CX_EVEN, Y0 - 44, "even", 12, "middle", fill="#777")
rect(480, Y0 - 34, 140, 20 * DY + 12, fill="#2b2f36", stroke="#111", sw=2, r=14)

for pin in range(1, 41):
    kind, label = HEADER[pin]
    row = (pin - 1) // 2
    y = Y0 + row * DY
    odd = pin % 2 == 1
    cx = CX_ODD if odd else CX_EVEN
    used = USED.get(pin)
    if pin == 1:
        rect(cx - 12, y - 12, 24, 24, fill=FILL[kind], stroke=used[0] if used else "#111", sw=4 if used else 1, r=3)
    else:
        dot(cx, y, 12, FILL[kind], ring=used[0] if used else None)
    text(cx, y + 4, str(pin), 11, "middle", True, "#fff" if kind in ("5v", "gnd", "3v3") else "#222")
    # boot level: GPIO 0-8 are pulled HIGH by the Pi from power-on (safe for active-low relays)
    gpio_n = int(label.split()[1]) if label.startswith("GPIO") else None
    colour = "#a61e1e" if kind == "id" else "#2b8a3e" if gpio_n is not None and gpio_n <= 8 else "#555"
    bold = used is not None or (gpio_n is not None and gpio_n <= 8)
    if odd:
        text(470, y + 5, label, 14, "end", bold, colour)
    else:
        text(630, y + 5, label, 14, "start", bold, colour)
    if used:
        col, what = used
        if odd:
            rect(40, y - 17, 262, 34, fill="#fff", stroke=col, sw=3, r=8)
            text(52, y + 5, what, 14, "start", True, "#222")
        else:
            rect(798, y - 17, 262, 34, fill="#fff", stroke=col, sw=3, r=8)
            text(810, y + 5, what, 14, "start", True, "#222")

# ------------------------------------------------------------- orientation
yb = Y0 + 20 * DY + 20
rect(40, yb, 500, 150, fill="#fff", stroke="#999", sw=1.5)
text(56, yb + 26, "Finding pin 1", 15, bold=True)
for i, s in enumerate([
    "Pin 1 (the square one) is at the end of the header",
    "nearest the SD card slot. Odd pins are the row on the",
    "inner side; even pins (2, 4, 6 \u2026) run along the board\u2019s",
    "outer edge, so the 5V pins sit at the outer corner.",
    "Count pins from the SD card end; check it before powering on.",
]):
    text(56, yb + 50 + i * 20, s, 12.5, fill="#333")

rect(560, yb, 500, 150, fill="#fff", stroke="#999", sw=1.5)
text(576, yb + 26, "config.toml names", 15, bold=True)
for i, s in enumerate([
    "sensor_pin = 4     DHT22 data      (pin 7)",
    "heat1_pin  = 2     relay IN1 / W1  (pin 3)",
    "cool_pin   = 3     relay IN2 / Y   (pin 5)",
    "heat2_pin  = 5     relay IN3 / W2  (pin 29)",
    "fan_pin    = 6     relay IN4 / G   (pin 31)",
]):
    text(576, yb + 52 + i * 19, s, 12.5, fill="#222")

# ------------------------------------------------------------------ legend
yl = yb + 172
x = 40
for fillc, name in [(FILL["3v3"], "3.3 V"), (FILL["5v"], "5 V"), (FILL["gnd"], "Ground"),
                    (FILL["gpio"], "GPIO"), (FILL["id"], "ID EEPROM (leave alone)")]:
    dot(x + 10, yl, 10, fillc)
    text(x + 28, yl + 5, name, 13)
    x += 28 + 9 * len(name) + 28
dot(x + 10, yl, 10, "#fff", ring="#1c7ed6")
text(x + 28, yl + 5, "used here", 13)
text(40, yl + 34, "Green GPIO names (GPIO 0\u20138) are pulled HIGH by the Pi from the moment power is applied. "
     "With active-low relays HIGH means OFF,", 12, fill="#2b8a3e")
text(40, yl + 52, "so a relay on one of those pins cannot click on during boot. GPIO 9\u201327 default LOW. "
     "GPIO 2 and 3 also have fixed 1.8k pull-ups on the board.", 12, fill="#2b8a3e")

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "gpio-pinmap.svg"), "w") as f:
        f.write(C.svg())
    C.png(os.path.join(OUT, "gpio-pinmap.png"), scale=1, ss=3)
    print("wrote docs/gpio-pinmap.svg and docs/gpio-pinmap.png")
