"""A scripted coding-agent terminal session (Claude Code's layout), rendered the
way Ink's log-update draws it, for a product that shows such a session in a web
terminal or a tmux pane.

Finished messages are static: written once, then they scroll. The bottom
region (a tool still running, the spinner, the input box and the mode line)
is redrawn in place on every change, by moving the cursor up over it and
clearing to the end of the screen.

    session = Session("~/project", banner("Claude Code", "v<installed>", "<model> · <plan>", "~/project"))
    session.at(1.0, lambda: session.add(user_block("<what the engineer types>")))
    session.at(2.5, lambda: session.add(text_block("<what the agent answers>")))
    viewport = Viewport(120, 32)   # per attached client: repaint() once, then update() per frame
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from webcap.ansi import (
    ADD_BG, AGENT, BORDER, DEL_BG, DIM, ERROR, SHIMMER, SUCCESS, USER_BG,
    Line, Style, encode, highlight_rust, pad, seg, width, wrap,
)

Block = Callable[[int], list[Line]]
SPINNER = "·✢✳✶✻✽✻✶✳✢"
PREFIX = "  ⎿  "
CONT = "     "


def blank() -> Line:
    return []


def text_block(text: str) -> Block:
    """An assistant message: a bullet and wrapped prose."""

    def render(cols: int) -> list[Line]:
        rows = wrap(text, cols - 2, "● ", "  ")
        lines = [[seg(rows[0][:2]), seg(rows[0][2:])]]
        lines += [[seg(row)] for row in rows[1:]]
        return [blank(), *lines]

    return render


def user_block(text: str) -> Block:
    def render(cols: int) -> list[Line]:
        rows = wrap(text, cols - 2, "> ", "  ")
        lines = [pad([seg(row, bg=USER_BG)], min(cols, max(width(r) for r in rows) + 1), USER_BG)
                 for row in rows]
        return [blank(), *lines]

    return render


def call_line(name: str, arg: str, dot: Style) -> Line:
    return [("●", dot), seg(" "), seg(name, bold=True), seg(f"({arg})")]


def tool_block(name: str, arg: str, result: list[Line]) -> Block:
    def render(cols: int) -> list[Line]:
        body = [[seg(PREFIX if i == 0 else CONT, DIM), *line] for i, line in enumerate(result)]
        return [blank(), call_line(name, arg, Style(fg=SUCCESS)), *body]

    return render


def running_block(name: str, arg: str, blink: bool, note: str = "Running…") -> Block:
    def render(cols: int) -> list[Line]:
        dot = Style(fg=DIM) if blink else Style(fg=(90, 90, 90))
        return [blank(), call_line(name, arg, dot), [seg(PREFIX, DIM), seg(note, DIM)]]

    return render


def todo_block(items: list[tuple[str, str]]) -> Block:
    """items: (state, text) with state in done / active / open."""

    def render(cols: int) -> list[Line]:
        lines: list[Line] = [blank(), [seg("●", SUCCESS), seg(" "), seg("Update Todos", bold=True)]]
        for i, (state, text) in enumerate(items):
            lead = seg(PREFIX if i == 0 else CONT, DIM)
            if state == "done":
                lines.append([lead, seg("☒ ", DIM), seg(text, DIM, strike=True)])
            elif state == "active":
                lines.append([lead, seg("☐ ", bold=True), seg(text, bold=True)])
            else:
                lines.append([lead, seg("☐ "), seg(text)])
        return lines

    return render


def diff_block(path: str, summary: str, hunk: list[tuple[str, int, str]]) -> Block:
    """hunk rows: (kind, line number, code) with kind in ' ', '+', '-'."""

    def render(cols: int) -> list[Line]:
        lines: list[Line] = [
            blank(),
            call_line("Update", path, Style(fg=SUCCESS)),
            [seg(PREFIX, DIM), seg(summary, DIM)],
        ]
        for kind, number, code in hunk:
            bg = ADD_BG if kind == "+" else DEL_BG if kind == "-" else None
            gutter = seg(f"{number:>6} ", DIM if bg is None else None, bg=bg)
            sign = seg(kind + " ", bg=bg)
            row: Line = [seg(CONT), gutter, sign, *highlight_rust(code, bg)]
            lines.append(pad(row, cols - 1, bg) if bg else row)
        return lines

    return render


def write_block(path: str, count: int, preview: list[str]) -> Block:
    def render(cols: int) -> list[Line]:
        lines: list[Line] = [
            blank(),
            call_line("Write", path, Style(fg=SUCCESS)),
            [seg(PREFIX, DIM), seg(f"Wrote {count} lines to ", DIM), seg(path, bold=True)],
        ]
        for i, code in enumerate(preview, start=1):
            lines.append([seg(CONT), seg(f"{i:>6} ", DIM), *highlight_rust(code)])
        lines.append([seg(CONT), seg(f"     … +{count - len(preview)} lines (ctrl+o to expand)", DIM)])
        return lines

    return render


def banner(title: str, version: str, subtitle: str, cwd: str) -> Block:
    """The agent's start banner; show the version that is actually installed."""
    def render(cols: int) -> list[Line]:
        return [
            [seg(" ▐▛███▜▌", AGENT), seg("   "), seg(title, bold=True), seg(f" {version}", DIM)],
            [seg("▝▜█████▛▘", AGENT), seg("  "), seg(subtitle, DIM)],
            [seg("  ▘▘ ▝▝ ", AGENT), seg("   "), seg(cwd, DIM)],
        ]

    return render


def compact(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def clock(secs: float) -> str:
    s = int(secs)
    return f"{s // 60}m {s % 60}s" if s >= 60 else f"{s}s"


@dataclass
class Spinner:
    verb: str
    since: float
    tokens: int
    rate: float

    def line(self, t: float) -> Line:
        glyph = SPINNER[int(t * 1000 / 120) % len(SPINNER)]
        word = self.verb + "…"
        span = len(word) + 8
        head = int(t * 1000 / 70) % span - 3
        out: Line = [seg(glyph + " ", AGENT)]
        for i, ch in enumerate(word):
            out.append(seg(ch, SHIMMER if head <= i < head + 3 else AGENT))
        tokens = self.tokens + int(max(0.0, t - self.since) * self.rate)
        out.append(seg(f" ({clock(t - self.since)} · ↓ {compact(tokens)} tokens · esc to interrupt)", DIM))
        return out


class Session:
    """The session's transcript and bottom region at clip time `t`."""

    def __init__(self, cwd: str, header: Block | None = None) -> None:
        self.cwd = cwd
        self.t = 0.0
        self.blocks: list[Block] = [header] if header else []
        self.pending: tuple[str, str, str] | None = None
        self.spinner: Spinner | None = None
        self.input = ""
        self._events: list[tuple[float, Callable[[], None]]] = []
        self.on_submit: Callable[[str, float], None] | None = None

    def at(self, t: float, action: Callable[[], None]) -> None:
        self._events.append((t, action))
        self._events.sort(key=lambda e: e[0])

    def cancel_scheduled(self) -> None:
        """Drop the rest of the script: the user steered the session elsewhere."""
        self._events = []

    def add(self, block: Block) -> None:
        self.blocks.append(block)

    def advance(self, t: float) -> None:
        self.t = t
        while self._events and self._events[0][0] <= t:
            _, action = self._events.pop(0)
            action()

    def keystrokes(self, data: bytes) -> None:
        text = data.decode("utf-8", "replace")
        if text.startswith("\x1b"):
            return
        for ch in text:
            if ch == "\r":
                message, self.input = self.input.strip(), ""
                if message and self.on_submit:
                    self.on_submit(message, self.t)
            elif ch in "\x7f\b":
                self.input = self.input[:-1]
            elif ch.isprintable():
                self.input += ch

    def dynamic(self, cols: int) -> list[Line]:
        lines: list[Line] = []
        if self.pending:
            name, arg, note = self.pending
            lines += running_block(name, arg, int(self.t * 2) % 2 == 0, note)(cols)
        lines.append(blank())
        if self.spinner:
            lines.append(self.spinner.line(self.t))
            lines.append(blank())
        rule = [seg("─" * cols, BORDER)]
        prompt: Line = [seg("> ", BORDER), seg(self.input), (" ", Style(inverse=True))]
        mode = [seg("  ⏵⏵ bypass permissions on", ERROR), seg(" (shift+tab to cycle)", DIM)]
        return lines + [rule, prompt, rule, mode]


class Viewport:
    """One attached client: what it has drawn, so updates stay incremental."""

    def __init__(self, cols: int, rows: int) -> None:
        self.cols = cols
        self.rows = rows
        self.blocks_done = 0
        self.dyn_height = 0
        self.last_dynamic = ""

    def repaint(self, session: Session) -> str:
        lines: list[Line] = []
        for block in session.blocks:
            lines += block(self.cols)
        dynamic = session.dynamic(self.cols)
        tail = [encode(line) for line in (lines + dynamic)[-self.rows:]]
        self.blocks_done = len(session.blocks)
        self.dyn_height = len(dynamic)
        self.last_dynamic = "\r\n".join(encode(line) for line in dynamic)
        return "\x1b[?25l\x1b[0m\x1b[H\x1b[2J" + "\r\n".join(tail)

    def update(self, session: Session) -> str | None:
        fresh = session.blocks[self.blocks_done:]
        dynamic = session.dynamic(self.cols)
        encoded = "\r\n".join(encode(line) for line in dynamic)
        if not fresh and encoded == self.last_dynamic:
            return None
        out = ["\r"]
        if self.dyn_height > 1:
            out.append(f"\x1b[{self.dyn_height - 1}A")
        out.append("\x1b[J")
        for block in fresh:
            for line in block(self.cols):
                out.append(encode(line) + "\r\n")
        out.append(encoded)
        self.blocks_done = len(session.blocks)
        self.dyn_height = len(dynamic)
        self.last_dynamic = encoded
        return "".join(out)

