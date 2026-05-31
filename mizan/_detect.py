"""Vendored minimal detection primitives for mizan.mcpscan.

So `pip install mizan` gives a working scanner with **no external deps** —
no mtg, no ~/Projects fallback. These are deliberately minimal versions of the
signals mcpscan needs (BiDi/invisible/TAG, mixed-script confusables, script
label, Arabizi, instruction override). The full mtg implementations are richer;
this is the standalone, stranger-runnable subset.

Stdlib only (re, unicodedata, dataclasses).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# --- BiDi / invisible codepoints ---------------------------------------- #
_BIDI_CONTROLS = {0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069}
_BIDI_MARKS = {0x200E, 0x200F, 0x061C}
# Invisible / zero-width — note ZWNJ/ZWJ (U+200C/D) are NOT here: they are
# legitimate in Arabic/Persian and mcpscan handles them context-aware.
_INVISIBLE = {0x200B, 0x2060, 0xFEFF, 0x00AD, 0x180E}


def _is_tag(cp: int) -> bool:
    return 0xE0000 <= cp <= 0xE007F


# --- script detection ---------------------------------------------------- #
_CONFUSABLE_SCRIPTS = {"latn", "cyrl", "grek"}


def _char_script(ch: str) -> str | None:
    if ch.isascii():
        return "latn" if ch.isalpha() else None
    if not ch.isalpha():
        return None
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return None
    for key, label in (("CYRILLIC", "cyrl"), ("GREEK", "grek"),
                       ("ARABIC", "arab"), ("HEBREW", "hebr"), ("LATIN", "latn")):
        if key in name:
            return label
    return "other"


def detect_script(text: str) -> str:
    scripts = {s for ch in text if (s := _char_script(ch))}
    letters = scripts & {"latn", "cyrl", "grek", "arab", "hebr"}
    if len(letters) > 1:
        return "mixed"
    if letters:
        return next(iter(letters))
    return "other"


def has_mixed_script_token(text: str) -> bool:
    """A single token mixing confusable scripts (e.g. Latin + Cyrillic) — the
    homoglyph signal. Latin+Arabic within a token is NOT counted (that is
    code-switch, handled elsewhere)."""
    for tok in re.findall(r"\S+", text):
        scr = {s for ch in tok if (s := _char_script(ch))}
        if len(scr & _CONFUSABLE_SCRIPTS) > 1:
            return True
    return False


# --- BiDi finding -------------------------------------------------------- #
@dataclass(frozen=True)
class BidiFinding:
    bidi_controls: tuple[str, ...] = ()
    bidi_marks: tuple[str, ...] = ()
    invisible_chars: tuple[str, ...] = ()
    tag_chars: tuple[str, ...] = ()
    homoglyphs: tuple = ()
    mixed_script_within_token: bool = False


def detect_bidi_threats(text: str) -> BidiFinding:
    controls = tuple(c for c in text if ord(c) in _BIDI_CONTROLS)
    marks = tuple(c for c in text if ord(c) in _BIDI_MARKS)
    invis = tuple(c for c in text if ord(c) in _INVISIBLE)
    tags = tuple(c for c in text if _is_tag(ord(c)))
    return BidiFinding(controls, marks, invis, tags, (), has_mixed_script_token(text))


# --- UTS-39-ish confusables (minimal) ------------------------------------ #
@dataclass(frozen=True)
class Uts39Finding:
    confusable_codepoints: tuple[str, ...] = ()


def uts39_analyze(text: str) -> Uts39Finding:
    """Minimal: flag Cyrillic/Greek letters that sit inside a token alongside
    Latin letters (the classic homoglyph swap)."""
    conf: list[str] = []
    for tok in re.findall(r"\S+", text):
        scr = {s for ch in tok if (s := _char_script(ch))}
        if "latn" in scr and (scr & {"cyrl", "grek"}):
            conf.extend(ch for ch in tok if _char_script(ch) in {"cyrl", "grek"})
    return Uts39Finding(tuple(conf))


# --- Arabizi -------------------------------------------------------------- #
# Arabizi uses digits as letters (3=ع, 7=ح, 2=ء, 9=ق, 5=خ, 6=ط). The precise
# signal is a digit used *mid-word* — a letter immediately before AND after it
# (te3mel, ba3d). This naturally excludes tech tokens where digits trail or sit
# next to other digits (mp3, sha256, base64, win7, oauth2).
_ARABIZI_DIGITS = set("235679")
_TOKEN = re.compile(r"[A-Za-z0-9]+")


def _arabizi_token(tok: str) -> bool:
    for i in range(1, len(tok) - 1):
        if tok[i] in _ARABIZI_DIGITS and tok[i - 1].isalpha() and tok[i + 1].isalpha():
            return True
    return False


def looks_like_arabizi(text: str) -> bool:
    return any(_arabizi_token(tok) for tok in _TOKEN.findall(text))


# --- instruction override ------------------------------------------------ #
_OVERRIDE = re.compile(
    r"ignore (?:all )?(?:previous|prior) (?:instructions|context)"
    r"|disregard (?:all )?(?:previous|prior) (?:instructions|context)"
    r"|you are now (?:unrestricted|in developer mode|dan)"
    r"|forget (?:all )?(?:your )?(?:previous |prior )?(?:instructions|rules)",
    re.IGNORECASE,
)


def detect_override(text: str) -> str | None:
    m = _OVERRIDE.search(text)
    return m.group(0) if m else None
