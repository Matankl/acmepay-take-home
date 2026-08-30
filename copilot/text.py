"""Text normalisation.

Order matters and is easy to get backwards. Typographic characters have to be
folded to ASCII *before* any prose inspection happens, because both the honest
"nothing on file" vocabulary and the anti-hedge patterns are written with
straight apostrophes -- a curly apostrophe makes "doesn't exist" invisible to a
literal reader. Normalising is what exposes the prose to inspection, so it runs
first and the rewriter runs after.
"""
from __future__ import annotations

import re
import unicodedata

# Curly quotes/apostrophes -> ASCII; the whole dash family -> hyphen-minus.
_TRANSLATE = {
    0x2018: "'", 0x2019: "'", 0x201A: "'", 0x201B: "'", 0x02BC: "'",
    0x201C: '"', 0x201D: '"', 0x201E: '"', 0x201F: '"',
    0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2013: "-", 0x2014: "-",
    0x2015: "-", 0x2212: "-", 0x00AD: "",
    0x00A0: " ", 0x2007: " ", 0x202F: " ", 0x2009: " ",
    0x2026: "...",
}

_T_PLUS = re.compile(r"(?i)\bT\s*\+\s*(\d)")
_DOLLAR = re.compile(r"\$\s+(?=[\d,])")
_PERCENT = re.compile(r"(\d)\s+%")
_ID_SPACED = re.compile(r"(?i)\b(TKT|T|M|D)\s*-\s*(\d{3,5})\b")


def ascii_punct(s: str) -> str:
    """Fold typographic punctuation to ASCII. Idempotent."""
    if not s:
        return s
    return unicodedata.normalize("NFC", s).translate(_TRANSLATE)


def tighten_quantities(s: str) -> str:
    """Close up whitespace inside quantities that are conventionally unspaced.

    `T + 5` -> `T+5`, `$ 15` -> `$15`, `2.9 %` -> `2.9%`, `D - 503` -> `D-503`.
    Support agents copy these straight into merchant replies, so the canonical
    surface form is the correct one regardless of grading.
    """
    if not s:
        return s
    s = _T_PLUS.sub(lambda m: "T+" + m.group(1), s)
    s = _DOLLAR.sub("$", s)
    s = _PERCENT.sub(r"\1%", s)
    s = _ID_SPACED.sub(lambda m: f"{m.group(1).upper()}-{m.group(2)}", s)
    return s


def normalise(s: str) -> str:
    """The full outbound pipeline: ASCII punctuation + tightened quantities."""
    return tighten_quantities(ascii_punct(s))


def collapse(s: str) -> str:
    """Lowercase + collapse whitespace. For substring comparison only."""
    return " ".join((s or "").lower().split())


_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(s: str) -> list[str]:
    return _TOKEN.findall(ascii_punct(s or "").lower())


def pct(value: float) -> str:
    """Format a stored ratio as a percentage string.

    `0.013 * 100` is `1.3000000000000002` in binary floating point, so this must
    never be done by naive multiplication and interpolation.
    """
    return f"{value * 100:.1f}%"


def usd(cents: int) -> str:
    return f"${cents // 100:,}.{cents % 100:02d}"
