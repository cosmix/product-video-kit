"""Drum patterns on the bar grid: kick, clap, shaker 16ths, tambourine,
tom builds, cymbal swells and risers. Everything straight, nothing brushed."""

from __future__ import annotations

from .score import Score

SHAKER_16 = (0, -10, -5, -9)     # velocity offsets per 16th; e and a lighter


def shaker(sc: Score, start: float, end: float, vel: int, div: int = 16) -> None:
    step = 4.0 / div
    n = int(round((end - start) * div))
    first = int(round((start - int(start)) * div))
    for k in range(n):
        idx = first + k
        off = SHAKER_16[idx % 4] if div == 16 else (0 if idx % 2 == 0 else -8)
        sc.hit("shaker", start * 4 + k * step, vel + off, jitter=0.004)


def backbeat(sc: Score, start: float, end: float, vel: int, kind: str = "clap",
             with_snare: bool = False) -> None:
    """Claps (or snaps) on 2 and 4; an optional soft snare under the claps."""
    bar = start
    while bar < end - 1e-6:
        for b in (1, 3):
            if bar + b / 4 < end:
                sc.hit(kind, bar * 4 + b, vel)
                if with_snare:
                    sc.hit("snare", bar * 4 + b, vel - 16)
        bar += 1


def kick(sc: Score, start: float, end: float, vel: int, four: bool = False,
         push: bool = False, body: bool = True) -> None:
    """Kick on 1 and 3, or four on the floor; `push` adds the '&' of 4 into the
    next bar. `body` layers the orchestral bass drum underneath."""
    bar = start
    while bar < end - 1e-6:
        beats = (0, 1, 2, 3) if four else (0, 2)
        for b in beats:
            if bar + b / 4 < end:
                v = vel if b in (0, 2) else vel - 8
                sc.hit("kick", bar * 4 + b, v)
                if body and b in (0, 2):
                    sc.hit("bdrum", bar * 4 + b, v - 30)
        if push and bar + 1 <= end:
            sc.hit("kick", bar * 4 + 3.5, vel - 12)
        bar += 1


def tambourine(sc: Score, start: float, end: float, vel: int, pattern: str = "offbeats") -> None:
    """offbeats: every '&'; twofour: 2 and 4 with the down stroke; sync: the
    3-3-2 shape (1, 2&, 4) plus the '&' of 1."""
    shapes = {"offbeats": (0.5, 1.5, 2.5, 3.5), "twofour": (1, 3), "sync": (0.5, 1.5, 3, 3.5)}
    bar = start
    while bar < end - 1e-6:
        offs = shapes[pattern]
        for b in offs:
            if bar + b / 4 < end:
                sc.hit("tamb", bar * 4 + b, vel + (10 if pattern != "offbeats" else 0))
        bar += 1


def clicks(sc: Score, start: float, end: float, vel: int) -> None:
    """Rim clicks on the 'e' of 1 and 3 and the 'a' of 2 and 4: a light syncopated tick."""
    bar = start
    while bar < end - 1e-6:
        for b in (0.25, 1.75, 2.25, 3.75):
            if bar + b / 4 < end:
                sc.hit("click", bar * 4 + b, vel)
        bar += 1


def fill(sc: Score, bar: float, vel: int, beats: float = 1.0) -> None:
    """Tom fill over the last `beats` of the bar ending at `bar` (a downbeat)."""
    n = int(beats * 4)
    for k in range(n):
        inst = "tom_hi" if k < n // 2 else "tom_lo"
        sc.hit(inst, bar * 4 - beats + k * 0.25, vel - 10 + 14 * k / max(1, n - 1))
    sc.hit("cym_hit", bar * 4, vel - 6)


def build(sc: Score, start: float, end: float, vel: int, riser: bool = True,
          toms: bool = True, taiko: bool = True) -> None:
    """Crescendo into the downbeat at `end`: tom 8ths rising, taiko on the beats,
    a cymbal swell peaking on the downbeat and a noise riser."""
    beats = (end - start) * 4
    n = int(beats * 2)
    for k in range(n):
        u = k / max(1, n - 1)
        if toms:
            sc.hit("tom_lo" if k % 4 == 0 else "tom_hi", start * 4 + k * 0.5, vel - 24 + 30 * u)
        if taiko and k % 2 == 0 and u > 0.4:
            sc.hit("taiko", start * 4 + k * 0.5, vel - 30 + 30 * u)
    sc.hit("cym_swell" if beats >= 3 else "cym_swell_short", end * 4, vel, beats=beats)
    if riser:
        sc.hit("riser", end * 4, vel, beats=beats)


def crash(sc: Score, bar: float, vel: int, drop: bool = True) -> None:
    sc.hit("cym_hit", bar * 4, vel)
    sc.hit("taiko", bar * 4, vel - 6)
    sc.hit("bdrum", bar * 4, vel - 10)
    if drop:
        sc.hit("sub_drop", bar * 4, vel - 4)
