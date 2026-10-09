"""Chord symbols, chord-tone lookup and voice-led voicings."""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from functools import lru_cache

PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

QUALITIES = {
    "": (0, 4, 7), "m": (0, 3, 7), "sus2": (0, 2, 7), "sus4": (0, 5, 7),
    "add9": (0, 4, 7, 14), "madd9": (0, 3, 7, 14), "6": (0, 4, 7, 9), "6/9": (0, 4, 7, 9, 14),
    "m7": (0, 3, 7, 10), "maj7": (0, 4, 7, 11), "7sus4": (0, 5, 7, 10),
    "add#11": (0, 4, 7, 18), "5": (0, 7, 12),
}


def pc_of(name: str) -> int:
    return (PC[name[0]] + name[1:].count("#") - name[1:].count("b")) % 12


@dataclass(frozen=True)
class Chord:
    symbol: str
    root: int                     # pitch class
    intervals: tuple[int, ...]
    bass: int                     # pitch class

    @property
    def pcs(self) -> set[int]:
        return {(self.root + i) % 12 for i in self.intervals}

    def guide_tones(self) -> set[int]:
        """Third (or sus substitute) and seventh: what makes the colour."""
        g = {i % 12 for i in self.intervals if i % 12 in (2, 3, 4, 5, 10, 11)}
        return {(self.root + i) % 12 for i in g}


@lru_cache(maxsize=None)
def chord(symbol: str) -> Chord:
    m = re.fullmatch(r"([A-G][b#]?)(6/9|[^/]*)(?:/([A-G][b#]?))?", symbol)
    if not m or m.group(2) not in QUALITIES:
        raise ValueError(f"unknown chord {symbol!r}")
    root = pc_of(m.group(1))
    bass = pc_of(m.group(3)) if m.group(3) else root
    return Chord(symbol, root, QUALITIES[m.group(2)], bass)


def nearest(pc: int, target: float, lo: int = 0, hi: int = 127) -> int:
    """MIDI note with pitch class pc nearest to target within [lo, hi]."""
    base = int(target) - ((int(target) - pc) % 12)
    cands = [n for n in (base - 12, base, base + 12, base + 24) if lo <= n <= hi]
    return min(cands, key=lambda n: abs(n - target))


def above(pc: int, floor: int) -> int:
    """Lowest MIDI note with pitch class pc at or above `floor`."""
    return floor + ((pc - floor) % 12)


def voice(ch: Chord, n: int, lo: int, hi: int, prev: list[int] | None = None,
          top: int | None = None) -> list[int]:
    """Choose n chord tones in [lo, hi], smoothest from prev, guide tones kept.

    `top` pins the highest voice (melody note) when given.
    """
    pool = [p for p in range(lo, hi + 1) if p % 12 in ch.pcs and (top is None or p < top)]
    k = n - (1 if top is not None else 0)
    guides = ch.guide_tones()
    center = (lo + hi) / 2
    best, best_cost = None, float("inf")
    for combo in itertools.combinations(pool, k):
        notes = sorted(combo + ((top,) if top is not None else ()))
        gaps = [b - a for a, b in zip(notes, notes[1:])]
        if any(g < 2 for g in gaps) or any(g > 9 for g in gaps[1:]) or (gaps and gaps[0] > 12):
            continue
        present = {x % 12 for x in notes}
        cost = 4.0 * len(guides - present)
        cost += 1.5 * max(0, len(ch.pcs) - 1 - len(present))
        if len(present) < len(notes):
            cost += 3.0
        if prev:
            cost += sum(min(abs(a - b) for b in prev) for a in notes) * 0.6
            cost += abs(max(notes) - max(prev)) * 0.4
        else:
            cost += abs(sum(notes) / len(notes) - center) * 0.3
        if cost < best_cost:
            best, best_cost = notes, cost
    if best is None:
        raise ValueError(f"cannot voice {ch.symbol} in {lo}-{hi}")
    return best
