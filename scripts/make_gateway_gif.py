"""Render the gateway GIF: Mizan in front of an agent's tools — scan, gate,
sign, log. Every line is verbatim from a real `mizan gateway` run.

    python scripts/make_gateway_gif.py
"""

from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.expanduser("~/Downloads")
MONO = "/System/Library/Fonts/Menlo.ttc"

BG = (10, 11, 13)
PANEL = (15, 17, 21)
WHITE = (233, 236, 239)
DIM = (120, 128, 138)
CYAN = (45, 212, 191)
GREEN = (74, 222, 128)
AMBER = (245, 191, 79)
RED = (248, 113, 113)

# (text, color) — verbatim from a real gateway run + verify-log.
LINES = [
    ("$ mizan gateway --config mcp.json --receipt-log receipts.jsonl", CYAN),
    ("[gateway] up · gate=on · signing=hmac", DIM),
    ("", WHITE),
    ("  client → tools/list", DIM),
    ("[gateway] FLAGGED tool poisoned_tool: 2 finding(s) [medium]", AMBER),
    ("", WHITE),
    ("  client → tools/call safe_echo", DIM),
    ("[gateway] ALLOWED tools/call safe_echo → signed receipt", GREEN),
    ("", WHITE),
    ("  client → tools/call delete_db", DIM),
    ("[gateway] BLOCKED tools/call delete_db  (never reached your server)", RED),
    ("", WHITE),
    ("$ mizan report receipts.jsonl", CYAN),
    ("✓ chain intact: 3 link(s), all signatures valid", GREEN),
    ("", WHITE),
    ("scan · gate · prove · audit — every action, one signed receipt.", CYAN),
]


def _font(size):
    return ImageFont.truetype(MONO, size)


def _frame(n, W, H, fnt, title_fnt):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([20, 20, W - 20, H - 20], radius=18, fill=PANEL)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([50 + i * 34, 46, 70 + i * 34, 66], fill=c)
    d.text((W // 2 - 130, 44), "mizan gateway — scan · gate · sign · log", font=title_fnt, fill=DIM)
    y = 110
    for text, color in LINES[:n]:
        d.text((58, y), text, font=fnt, fill=color)
        y += 40
    return img


def main():
    W, H = 1240, 110 + 40 * len(LINES) + 30
    fnt, title_fnt = _font(25), _font(23)
    frames, durations = [], []
    for n in range(1, len(LINES) + 1):
        frames.append(_frame(n, W, H, fnt, title_fnt))
        durations.append(720 if LINES[n - 1][1] in (GREEN, AMBER, RED) else 360)
    frames += [frames[-1]] * 6
    durations += [450] * 6
    path = os.path.join(OUT, "mizan-gateway.gif")
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True)
    print("gif:", path)


if __name__ == "__main__":
    main()
