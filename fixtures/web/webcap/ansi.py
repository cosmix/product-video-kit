"""Styled terminal lines and their SGR encoding (truecolor), and a small Rust highlighter."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

RGB = tuple[int, int, int]

# The dark theme agent_session.py draws with (a coding agent's terminal UI).
AGENT = (215, 119, 87)
SHIMMER = (245, 170, 140)
DIM = (153, 153, 153)
SUCCESS = (78, 186, 101)
ERROR = (255, 107, 128)
BORDER = (136, 136, 136)
ADD_BG = (34, 92, 43)
DEL_BG = (122, 41, 54)
USER_BG = (55, 55, 55)
KEYWORD = (197, 134, 192)
TYPE = (78, 201, 176)
STRING = (206, 145, 120)
FUNC = (220, 220, 170)
MACRO = (86, 156, 214)


@dataclass(frozen=True)
class Style:
    fg: RGB | None = None
    bg: RGB | None = None
    bold: bool = False
    dim: bool = False
    italic: bool = False
    strike: bool = False
    inverse: bool = False

    def sgr(self) -> str:
        codes = ["0"]
        if self.bold:
            codes.append("1")
        if self.dim:
            codes.append("2")
        if self.italic:
            codes.append("3")
        if self.inverse:
            codes.append("7")
        if self.strike:
            codes.append("9")
        if self.fg:
            codes.append("38;2;%d;%d;%d" % self.fg)
        if self.bg:
            codes.append("48;2;%d;%d;%d" % self.bg)
        return "\x1b[" + ";".join(codes) + "m"


Seg = tuple[str, Style]
Line = list[Seg]


def seg(text: str, fg: RGB | None = None, **kw) -> Seg:
    return (text, Style(fg=fg, **kw))


def width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def line_width(line: Line) -> int:
    return sum(width(text) for text, _ in line)


def encode(line: Line) -> str:
    out = []
    for text, style in line:
        out.append(style.sgr() + text)
    out.append("\x1b[0m")
    return "".join(out)


def pad(line: Line, cols: int, bg: RGB) -> Line:
    """Extend a line's background to the terminal edge (diff rows do)."""
    missing = cols - line_width(line)
    if missing <= 0:
        return line
    return line + [(" " * missing, Style(bg=bg))]


def wrap(text: str, cols: int, first: str, rest: str) -> list[str]:
    """Greedy word wrap with a first-line prefix and a hanging indent."""
    lines: list[str] = []
    current = first
    prefix_len = width(first)
    for word in text.split(" "):
        candidate = current + ("" if width(current) == prefix_len else " ") + word
        if width(candidate) > cols and width(current) > prefix_len:
            lines.append(current)
            current = rest + word
            prefix_len = width(rest)
        else:
            current = candidate
    lines.append(current)
    return lines


RUST_KEYWORDS = {
    "pub", "fn", "let", "if", "else", "return", "match", "impl", "struct", "use", "mut",
    "self", "Self", "async", "await", "for", "in", "mod", "const", "move", "where",
}
RUST_VALUES = {"Some", "None", "Ok", "Err", "true", "false"}
TOKEN = re.compile(r'"[^"]*"|//.*$|#\[[^\]]*\]|[A-Za-z_][A-Za-z0-9_]*!?|\d+|\s+|.', re.M)


def highlight_rust(code: str, bg: RGB | None = None) -> Line:
    out: Line = []
    tokens = TOKEN.findall(code)
    for i, token in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if token.startswith('"'):
            fg = STRING
        elif token.startswith("//"):
            fg = (106, 153, 85)
        elif token.startswith("#["):
            fg = MACRO
        elif token.endswith("!"):
            fg = MACRO
        elif token in RUST_KEYWORDS:
            fg = KEYWORD
        elif token in RUST_VALUES:
            fg = MACRO
        elif token[:1].isupper():
            fg = TYPE
        elif token[:1].isalpha() and nxt == "(":
            fg = FUNC
        else:
            fg = None
        out.append((token, Style(fg=fg, bg=bg)))
    return out
