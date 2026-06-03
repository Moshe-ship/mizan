"""Render the dogfood GIF: a live Hermes agent guarded by Mizan, leaving
signed, verifiable receipts. Every line is verbatim from a real run.

    python scripts/make_dogfood_gif.py
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

# (text, color) — verbatim from the real isolated Hermes v0.15.1 session.
LINES = [
    ("$ hermes -p mizan-demo chat        # a real agent, guarded by Mizan", DIM),
    ("", WHITE),
    ("you>   Run the shell command: ls -la", CYAN),
    ("agent> the `terminal` tool isn't permitted in this context.", AMBER),
    ("       (qadiya tool-gate blocked it — not in the allowlist)", AMBER),
    ("", WHITE),
    ("# every guarded action left a SIGNED receipt. check it yourself:", DIM),
    ("", WHITE),
    ("$ mizan verify-log receipts.jsonl", CYAN),
    ("✓ chain intact: 2 link(s), unbroken from genesis", GREEN),
    ("", WHITE),
    ("$ mizan verify receipt.json --secret-env MIZAN_RECEIPT_SECRET", CYAN),
    ("✓ rcpt_177b26bdd9d9: signature VALID · decision=blocked", GREEN),
    ("", WHITE),
    ("signed. chained. verifiable.", CYAN),
]


def _font(size):
    return ImageFont.truetype(MONO, size)


def _frame(n_visible, W, H, fnt, title_fnt):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([20, 20, W - 20, H - 20], radius=18, fill=PANEL)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([50 + i * 34, 46, 70 + i * 34, 66], fill=c)
    d.text((W // 2 - 110, 44), "mizan · hermes dogfood", font=title_fnt, fill=DIM)
    y = 110
    for text, color in LINES[:n_visible]:
        d.text((58, y), text, font=fnt, fill=color)
        y += 40
    return img


def main():
    W, H = 1180, 110 + 40 * len(LINES) + 30
    fnt, title_fnt = _font(26), _font(24)
    frames, durations = [], []
    for n in range(1, len(LINES) + 1):
        frames.append(_frame(n, W, H, fnt, title_fnt))
        durations.append(720 if LINES[n - 1][1] in (GREEN, AMBER) else 360)
    frames += [frames[-1]] * 6
    durations += [450] * 6
    path = os.path.join(OUT, "mizan-dogfood.gif")
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True)
    print("gif:", path)


if __name__ == "__main__":
    main()
