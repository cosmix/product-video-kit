"""Shots of a tmux session: an isolated tmux server, and an operator's shell recorded while
typing into it (attaching to a session, steering a program in a pane).

Isolation: TMUX_TMPDIR points into the fixture folder, so the socket lives there and the
operator's own tmux server is never contacted; `-f` names the fixture's config so ~/.tmux.conf
is not read; the server is killed afterwards.

    with tmux_server("capture", FIXTURE / "tmux-tmp", clean_env(HOME), conf) as (tmux, env):
        tmux("new-session", "-d", "-s", "main", "-x", "120", "-y", "32", "-c", str(WS), "<pane command>")
        rec, typed = record_shell(WS, env, 120, 32, [(0.5, "tmux -L capture attach -t main")], total=6.0)
"""

from __future__ import annotations

import os
import random
import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from .capture import PROMPT_MARK, PROMPT_PATH, record_pty, typing_schedule
from .render import Recording


@contextmanager
def tmux_server(socket: str, tmpdir: Path, env: dict[str, str],
                conf: Path | None = None) -> Iterator[tuple[Callable[..., str], dict[str, str]]]:
    """Yield (tmux, env): tmux(*args) runs a command against the isolated server and returns
    its stdout; env is the environment to run the operator's shell with."""
    sock = tmpdir / f"tmux-{os.getuid()}" / socket
    if len(str(sock)) > 100:  # a Unix socket path holds about 104-108 bytes
        raise ValueError(f"tmux socket path too long ({len(str(sock))} bytes): {sock}; use a shorter tmpdir")
    tmpdir.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in env.items() if k != "TMUX"}
    env.update(TMUX_TMPDIR=str(tmpdir))
    base = ["tmux", "-L", socket] + (["-f", str(conf)] if conf else [])

    def tmux(*args: str) -> str:
        return subprocess.run([*base, *args], env=env, capture_output=True, text=True).stdout.strip()

    tmux("kill-server")
    try:
        yield tmux, env
    finally:
        tmux("kill-server")
        sock.unlink(missing_ok=True)


def _ps1(path: str) -> str:
    """bash's PS1 with the look of capture.prompt."""
    return f"\\[\\e[{PROMPT_PATH}m\\]{path}\\[\\e[0m\\] \\[\\e[{PROMPT_MARK}m\\]›\\[\\e[0m\\] "


def record_shell(cwd: Path, env: dict[str, str], cols: int, rows: int, lines: list[tuple[float, str]],
                 total: float, path: str = "~", seed: int = 7) -> tuple[Recording, list[dict]]:
    """Record an interactive bash in a pty while an operator types each (at, text) line at
    human cadence and presses Enter. Returns the recording and marks (typing starts, Enter)."""
    rng = random.Random(seed)
    actions, marks = [], [{"t": 0.0, "event": "shell prompt"}]
    for at, text in lines:
        keys, typed = typing_schedule(text, at, rng)
        actions += [*keys, (typed + 0.3, b"\r")]
        marks += [{"t": round(at, 3), "event": f"typing `{text}`"},
                  {"t": round(typed + 0.3, 3), "event": f"entered `{text}`"}]
    shell_env = {**env, "PS1": _ps1(path), "HISTFILE": "/dev/null", "INPUTRC": "/dev/null"}
    events, inputs = record_pty(["bash", "--norc", "--noprofile", "-i"], cwd, shell_env, cols, rows,
                                actions, total=total)
    return Recording(cols, rows, events, total, inputs, show_cursor=True), marks
