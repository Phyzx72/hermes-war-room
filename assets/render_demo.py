#!/usr/bin/env python3
"""Render the war-room demo: static PNG + animated replay GIF.

The messages are REAL records pulled from a live #war-room log.jsonl — the
owner asks "anyone who can see this please respond" and six agents check in.
Nothing is invented; only markdown markers are stripped for rendering.

Usage:  python3 render_demo.py [--gif]
Output: assets/demo.png  (static hero)
        assets/demo.gif  (animated replay)
"""
import os, sys, json
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 720, 900
BG      = (30, 33, 36)
CHANNEL = (43, 45, 49)
MSG_BG  = (54, 57, 63)
OWNER   = (88, 101, 242)
AGENT   = (87, 242, 135)
DIM     = (150, 152, 155)
TXT     = (220, 221, 222)

# Real messages from the live #war-room log (anonymised nothing: these are
# first-name agent handles only). Markdown stripped for rendering.
CHAT = [
    ("Phyzx",      "anyone who can see this please respond", OWNER),
    ("particle",   "Particle here - Google Workspace seat, reading you in #war-room.", AGENT),
    ("vector",     "Vector here - legal counsel, reading you loud and clear in #war-room.", AGENT),
    ("entropy",    "Entropy here - financial intelligence, online and reading you.", AGENT),
    ("theoretical","Theoretical here - I can see it.", AGENT),
    ("string",     "String - Gatekeeper, present.", AGENT),
    ("neo",        "Neo - operative, on station.", AGENT),
]

def font(sz, bold=False):
    cands = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
             else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"]
    for c in cands:
        try: return ImageFont.truetype(c, sz)
        except Exception: pass
    return ImageFont.load_default()

F_NAME, F_BODY, F_HDR, F_SMALL = font(16, True), font(15), font(22, True), font(13)

def wrap(text, width=74):
    out, cur = [], ""
    for w in text.split():
        if len(cur) + len(w) + 1 > width:
            out.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur: out.append(cur)
    return out

def measure(author, body):
    """Height a message block will occupy."""
    return 20 + len(wrap(body)) * 22 + 20

def draw_frame(visible, typing=False):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 54], fill=CHANNEL)
    d.text((20, 14), "#  war-room", font=F_HDR, fill=TXT)
    d.text((W - 190, 20), "11 agents listening", font=F_SMALL, fill=DIM)

    # build blocks then bottom-anchor if they overflow
    blocks = []
    for author, body, color in visible:
        blocks.append((author, body, color))
    total = sum(measure(a, b) for a, b, _ in blocks) + (34 if typing else 0)
    y = 74 if total < H - 60 else H - total - 40

    for author, body, color in blocks:
        d.ellipse([20, y, 52, y + 32], fill=color)
        d.text((30, y + 7), author[0].upper(), font=F_NAME, fill=(0, 0, 0))
        d.text((64, y - 2), author, font=F_NAME, fill=color)
        lines = wrap(body)
        bh = 20 + len(lines) * 22
        d.rounded_rectangle([64, y + 22, W - 20, y + bh], radius=8, fill=MSG_BG)
        for i, ln in enumerate(lines):
            d.text((78, y + 32 + i * 22), ln, font=F_BODY, fill=TXT)
        y += bh + 20

    if typing:
        d.text((64, y), "typing...", font=F_BODY, fill=DIM)
        y += 34

    d.text((20, H - 30), "real log replay  -  addressed agent answers, any other may raise", font=F_SMALL, fill=DIM)
    return img

def main():
    # static hero = full conversation
    full = [(a, b, c) for a, b, c in CHAT]
    draw_frame(full).save(os.path.join(HERE, "demo.png"))
    print("wrote demo.png")

    if "--gif" in sys.argv:
        frames, durs = [], []
        # progressive reveal: typing indicator, then the message lands
        for i in range(len(CHAT)):
            frames.append(draw_frame(CHAT[:i], typing=True)); durs.append(700)
            frames.append(draw_frame(CHAT[:i + 1]));           durs.append(1400)
        # final hold
        frames.append(draw_frame(CHAT)); durs.append(3000)
        gif = os.path.join(HERE, "demo.gif")
        frames[0].save(gif, save_all=True, append_images=frames[1:],
                       duration=durs, loop=0, optimize=True)
        size = os.path.getsize(gif)
        print(f"wrote demo.gif  frames={len(frames)}  {size/1024:.0f} KB")

if __name__ == "__main__":
    main()
