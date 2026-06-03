"""Render launch assets for Mizan — a static card (PNG) and a demo GIF.

No image model, no stock art: a clean card and a terminal-style animation of the
real pipeline flow, rendered with Pillow. Outputs to ~/Downloads.

    python scripts/make_assets.py
"""

from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.expanduser("~/Downloads")
MONO = "/System/Library/Fonts/Menlo.ttc"
SANS = "/System/Library/Fonts/SFNS.ttf"

BG = (10, 11, 13)
PANEL = (15, 17, 21)
WHITE = (233, 236, 239)
DIM = (120, 128, 138)
CYAN = (45, 212, 191)
GREEN = (74, 222, 128)
AMBER = (245, 191, 79)
RED = (248, 113, 113)


def font(path, size):
    return ImageFont.truetype(path, size)


# --------------------------------------------------------------------------- #
# Static launch card (1600x900)
# --------------------------------------------------------------------------- #
def make_card() -> str:
    W, H = 1600, 900
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    title = font(SANS, 92)
    sub = font(SANS, 40)
    step = font(MONO, 34)
    small = font(MONO, 30)
    tiny = font(MONO, 28)

    d.text((90, 90), "Mizan", font=title, fill=WHITE)
    d.text((96, 205), "signed evidence for agent actions", font=sub, fill=CYAN)

    # the pipeline flow
    stages = ["scan", "restore", "balance", "classify", "constrain", "verify"]
    x, y = 96, 330
    for i, s in enumerate(stages):
        d.text((x, y), s, font=step, fill=WHITE)
        x += d.textlength(s, font=step) + 26
        if i < len(stages) - 1:
            d.text((x, y), "→", font=step, fill=DIM)
            x += d.textlength("→", font=step) + 26
    d.text((x + 6, y), "→ Receipt", font=step, fill=CYAN)

    # what it proves — three lines
    rows = [
        (AMBER, "poisoned MCP tool, contradiction, transliteration  →  flagged & blocked"),
        (RED, "agent claimed a result that never ran  →  mizan verify: exit 5 (it lied)"),
        (GREEN, "verify with a public key only  ·  hash-chained, append-only audit trail"),
    ]
    yy = 440
    for color, text in rows:
        d.rectangle([96, yy + 12, 110, yy + 40], fill=color)
        d.text((132, yy), text, font=small, fill=WHITE)
        yy += 70

    # install + repo
    d.rounded_rectangle([90, 700, 1510, 800], radius=16, fill=PANEL)
    d.text((120, 728), '$ pip install "mizan[all]"', font=step, fill=GREEN)
    d.text((96, 835), "open source · on PyPI · every claim reproducible — github.com/Moshe-ship/mizan",
           font=tiny, fill=DIM)

    path = os.path.join(OUT, "mizan-card.png")
    img.save(path)
    return path


# --------------------------------------------------------------------------- #
# Animated demo GIF (terminal style, line-by-line reveal)
# --------------------------------------------------------------------------- #
LINES = [
    ("$ python -m mizan   # one agent turn, end to end", DIM),
    ("", WHITE),
    ("[1/8] SCAN       inspect the MCP tool descriptor", CYAN),
    ("      R-BIDI-001  bidi [high]  -> flagged", AMBER),
    ("[2/8] PREFLIGHT  restore + balance the request", CYAN),
    ("      contradiction caught  (ok = False)", AMBER),
    ("[3/8] TOOL GATE  classify the proposed call", CYAN),
    ("      book_flight  ->  allow", GREEN),
    ("[4/8] CONSTRAIN  Arabic argument integrity (mtg)", CYAN),
    ("      'Riyadh' transliterated  ->  BLOCKED", AMBER),
    ("[5/8] VERIFY     did the agent lie about the call?", CYAN),
    ("      claimed delete_db that never ran  ->  UNVERIFIED", RED),
    ("[6/8] RECEIPT    one signed evidence object (v0)", CYAN),
    ("      blocked by: mcpscan, mtg, toolproof", WHITE),
    ("[7/8] mizan verify   ->  signature VALID", GREEN),
    ("[8/8] tamper receipt ->  mizan verify: TAMPERED (exit 2)", RED),
    ("", WHITE),
    ("signed. verifiable. check it yourself.", CYAN),
]


def _frame(n_visible: int, W: int, H: int, fnt, title_fnt):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # window chrome
    d.rounded_rectangle([20, 20, W - 20, H - 20], radius=18, fill=PANEL)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([50 + i * 34, 46, 70 + i * 34, 66], fill=c)
    d.text((W // 2 - 70, 44), "mizan demo", font=title_fnt, fill=DIM)
    y = 110
    for text, color in LINES[:n_visible]:
        d.text((58, y), text, font=fnt, fill=color)
        y += 40
    return img


def make_gif() -> str:
    W, H = 1100, 110 + 40 * len(LINES) + 30
    fnt = font(MONO, 27)
    title_fnt = font(MONO, 24)
    frames = []
    durations = []
    for n in range(1, len(LINES) + 1):
        frames.append(_frame(n, W, H, fnt, title_fnt))
        # pause longer on the punchy result lines
        durations.append(700 if LINES[n - 1][1] in (RED, GREEN) else 380)
    # hold the final frame
    frames += [frames[-1]] * 6
    durations += [400] * 6

    path = os.path.join(OUT, "mizan-demo.gif")
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True)
    return path


if __name__ == "__main__":
    c = make_card()
    g = make_gif()
    print(f"card: {c}")
    print(f"gif:  {g}")
