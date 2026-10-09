"""Run programs in a pty and record their output bytes with timestamps."""

from __future__ import annotations

import os
import random
import re
import select
import sys
import time
from pathlib import Path
from typing import Callable

import ptyprocess
from wcwidth import wcswidth

from .render import Recording

# (seconds after the program starts, bytes to type) or a callable run at that time.
Action = tuple[float, bytes | Callable[[], None]]


def clean_env(home: Path | None, tz: str | None = None, drop: tuple[str, ...] = ()) -> dict[str, str]:
    """The caller's env with a pinned terminal and locale. `drop` names variable prefixes to
    remove (the product's own settings, so the operator's configuration never leaks into a
    capture); `home` replaces HOME, for a scratch home with fixture config."""
    env = {k: v for k, v in os.environ.items() if not (drop and k.startswith(drop))}
    utf8 = "en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8"  # macOS may lack C.UTF-8
    env.update(TERM="xterm-256color", COLORTERM="truecolor", LANG=utf8, LC_ALL=utf8)
    if home is not None:
        env["HOME"] = str(home)
    if tz is not None:
        env["TZ"] = tz
    return env


def record_pty(argv: list[str], cwd: Path, env: dict[str, str], cols: int, rows: int,
               actions: list[Action], total: float) -> tuple[list[tuple[float, bytes]], list[float]]:
    """Spawn `argv`, perform `actions` on schedule, and return (events, input times)."""
    proc = ptyprocess.PtyProcess.spawn(argv, cwd=str(cwd), env=env, dimensions=(rows, cols))
    start = time.monotonic()
    events: list[tuple[float, bytes]] = []
    inputs: list[float] = []
    pending = sorted(actions, key=lambda a: a[0])
    try:
        while True:
            now = time.monotonic() - start
            if now >= total:
                break
            while pending and pending[0][0] <= now:
                _, action = pending.pop(0)
                if callable(action):
                    action()
                else:
                    proc.write(action)
                    inputs.append(time.monotonic() - start)
            ready, _, _ = select.select([proc.fd], [], [], 0.005)
            if ready:
                try:
                    data = proc.read(65536)
                except EOFError:
                    break
                events.append((time.monotonic() - start, data))
    finally:
        if proc.isalive():
            proc.terminate(force=True)
    return events, inputs


PROMPT_PATH = "38;2;154;147;168"   # SGR of the prompt's directory
PROMPT_MARK = "1;38;2;236;232;242"  # SGR of its chevron


def prompt(path: str) -> bytes:
    """A synthetic shell prompt: the working directory, dimmed, then a light chevron."""
    return f"\x1b[{PROMPT_PATH}m{path}\x1b[0m \x1b[{PROMPT_MARK}m›\x1b[0m ".encode()


def run_capture_output(argv: list[str], cwd: Path, env: dict[str, str], cols: int) -> bytes:
    """Run a non-interactive command in a pty (so it colours) and return all output."""
    events, _ = record_pty(argv, cwd, env, cols, 200, [], total=120.0)
    return b"".join(data for _, data in events)


def _visual_rows(line: bytes, cols: int) -> int:
    text = re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]", b"", line).decode("utf-8", "replace")
    width = max(0, wcswidth(text))
    return max(1, -(-width // cols))


def typing_schedule(text: str, start: float, rng: random.Random) -> tuple[list[tuple[float, bytes]], float]:
    """Keystrokes at human cadence with jitter; returns (keys, time after the last one)."""
    keys = []
    t = start
    for i, ch in enumerate(text):
        keys.append((t, ch.encode()))
        delay = rng.gauss(0.05, 0.014)
        if ch == " ":
            delay += rng.uniform(0.02, 0.06)
        if ch == " " and text[i + 1: i + 3] == "--":
            delay += rng.uniform(0.04, 0.1)
        t += max(0.03, delay)
    return keys, t


def synth_cli(prompt: bytes, command: str, output: bytes, cols: int, rows: int,
              seed: int, lead: float = 0.9, tail: float = 2.2) -> tuple[Recording, list[dict]]:
    """Prompt, a human-cadence typed command, then the real output in line bursts.

    The output text is the command's own; it is only cut at a line boundary so
    it fits between the command line and the closing prompt.
    """
    max_rows = rows - 2
    rng = random.Random(seed)
    events: list[tuple[float, bytes]] = [(-0.01, b"\x1b[?25h" + prompt)]
    inputs: list[float] = []
    marks = [{"t": 0.0, "event": "prompt shown"}]
    marks.append({"t": lead, "event": "typing starts"})
    keys, t = typing_schedule(command, lead, rng)
    events += keys
    inputs += [at for at, _ in keys]
    marks.append({"t": round(t, 3), "event": "command typed"})
    t += 0.38
    events.append((t, b"\r\n"))
    inputs.append(t)
    marks.append({"t": round(t, 3), "event": "enter pressed"})
    t += 0.22
    lines = output.replace(b"\r\n", b"\n").split(b"\n")
    while lines and not lines[-1].strip():
        lines.pop()
    kept: list[bytes] = []
    used = 0
    for line in lines:
        need = _visual_rows(line, cols)
        if used + need > max_rows:
            break
        kept.append(line)
        used += need
    first = True
    i = 0
    while i < len(kept):
        burst = rng.randint(1, 4)
        chunk = b"".join(line + b"\x1b[0m\r\n" for line in kept[i:i + burst])
        events.append((t, chunk))
        if first:
            marks.append({"t": round(t, 3), "event": "output starts"})
            first = False
        i += burst
        t += rng.uniform(0.018, 0.05)
    events.append((t, prompt))
    inputs.append(t)
    marks.append({"t": round(t, 3), "event": "output done"})
    duration = t + tail
    return Recording(cols, rows, events, duration, inputs), marks
