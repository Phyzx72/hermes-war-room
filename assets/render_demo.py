#!/usr/bin/env python3
"""Render the war-room demo chat mockup (assets/demo.png).

Shows the whole pitch in one glance: walk in, address one agent, it answers,
another raises a hand. Pure Pillow, no dependencies beyond Pillow.
"""
from PIL import Image, ImageDraw, ImageFont
import os

OUT = os.path.join(os.path.dirname(__file__), "demo.png")
W, H = 720, 900
BG = (30, 33, 36)          # discord dark
CHANNEL = (43, 45, 49)     # channel header bar
MSG_BG = (54, 57, 63)
OWNER = (88, 101, 242)     # discord blurple
AGENT = (87, 242, 135)     # bot green
RAISE = (250, 168, 26)     # amber
TXT = (220, 221, 222)
DIM = (150, 152, 155)

def font(sz, bold=False):
    for name in ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, sz)
        except Exception:
            pass
    return ImageFont.load_default()

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# channel header
d.rectangle([0, 0, W, 54], fill=CHANNEL)
d.text((20, 14), "#  war-room", font=font(22, True), fill=TXT)
d.text((W-200, 20), "11 agents listening", font=font(13), fill=DIM)

y = 74
def msg(author, body, color, badge):
    global y
    f_name = font(16, True)
    f_body = font(15)
    # avatar circle
    d.ellipse([20, y, 52, y+32], fill=color)
    d.text((29, y+6), badge, font=font(14, True), fill=(0,0,0))
    # name + body
    d.text((64, y-2), author, font=f_name, fill=color)
    # wrap body
    words = body.split()
    lines, cur = [], ""
    for w in words:
        if len(cur)+len(w)+1 > 78:
            lines.append(cur); cur = w
        else:
            cur = (cur+" "+w).strip()
    if cur: lines.append(cur)
    bh = 20 + len(lines)*22
    d.rounded_rectangle([64, y+22, W-20, y+bh], radius=8, fill=MSG_BG)
    for i, ln in enumerate(lines):
        d.text((78, y+32+i*22), ln, font=f_body, fill=TXT)
    y += bh + 20

msg("Phyzx", "Morning crew — who's here?", OWNER, "P")
msg("quantum", "Keymaster on deck. All loops green.", AGENT, "Q")
msg("einstein", "Architect online. Nothing ships without a blueprint.", AGENT, "E")
msg("Phyzx", "newtonian — status on the deploy?", OWNER, "P")
msg("newtonian", "Pipeline green. 3 migrations reversible, one rollback test pending.", AGENT, "N")
msg("vector", "[RAISE] legal flag on migration #3's data handling before it ships.", RAISE, "V")

d.text((20, y+6), "addressed agent answers  \u00b7  any other agent can raise", font=font(15), fill=TXT)
img.save(OUT)
print("wrote", OUT, img.size)
