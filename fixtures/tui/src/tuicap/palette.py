"""Terminal palette: background and foreground from the project's design.json, the standard
ANSI colours softened. TRUECOLOR maps colours a program hard-codes (lower-case hex) onto the
palette, and the project fills it from fixtures/tui/product.py (README.md, "TUI capture")."""

from __future__ import annotations

import pyte.graphics

from . import design

BG = design.color("background").lstrip("#").lower()
FG = design.color("text").lstrip("#").lower()

# ANSI 0-15
ANSI16 = [
    "1e1e1e",  # black
    "ef7a6e",  # red
    "7fd49a",  # green
    "f0a860",  # yellow
    "7fb1f0",  # blue
    "c49af0",  # magenta
    "6fd0dc",  # cyan
    "a8a8a8",  # white (ratatui Gray)
    "7a7a7a",  # bright black: dimmed text (ratatui DarkGray)
    "f59a90",
    "9be3b0",
    "f5c285",
    "9cc5f5",
    "d6b6f6",
    "92dde6",
    FG,  # bright white -> foreground (ratatui White)
]

_NAMES = ["black", "red", "green", "brown", "blue", "magenta", "cyan", "white"]
_BY_NAME = {name: i for i, name in enumerate(_NAMES)}
_BY_NAME.update({"bright" + name: i + 8 for i, name in enumerate(_NAMES)})
# crossterm emits the 16 colours as `38;5;n`; pyte stores those as xterm hex.
_XTERM16 = {hexval: i for i, hexval in enumerate(pyte.graphics.FG_BG_256[:16])}

# Truecolours a captured program hard-codes -> palette hex; filled from product.TRUECOLOR.
TRUECOLOR: dict[str, str] = {}


def rgb(hexval: str) -> tuple[int, int, int]:
    return int(hexval[0:2], 16), int(hexval[2:4], 16), int(hexval[4:6], 16)


def resolve(color: str, default: str) -> str:
    """pyte colour (name, xterm hex, or truecolour hex) -> palette hex."""
    if color == "default":
        return default
    if color in _BY_NAME:
        return ANSI16[_BY_NAME[color]]
    color = color.lower()
    if color in _XTERM16:
        return ANSI16[_XTERM16[color]]
    return TRUECOLOR.get(color, color)
