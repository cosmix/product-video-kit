"""Reusable textures: ostinati, pulses, bass, melody rendering, string lines."""

from __future__ import annotations

from dataclasses import dataclass

from .score import Score
from .theory import Chord, above, nearest, voice

# straight-eighth accent shapes (velocity offsets per eighth of a bar)
ACCENT_332 = (12, -7, -3, 12, -7, -3, 12, -5)   # 3-3-2 drive, no swing
ACCENT_EVEN = (9, -5, 3, -5, 6, -5, 3, -5)


@dataclass
class Dyn:
    vel: int
    accent: tuple = ACCENT_EVEN


def _tones(ch: Chord, floor: int) -> dict[str, int]:
    """Chord tones above `floor`: root, third (or sus), fifth, ninth."""
    root = above(ch.root, floor)
    third_iv = next((i for i in ch.intervals if i in (3, 4, 5, 2)), 4)
    return {"r": root, "3": above((ch.root + third_iv) % 12, root),
            "5": above((ch.root + 7) % 12, root), "9": above((ch.root + 2) % 12, root),
            "r8": root + 12}


def ostinato(sc: Score, inst: str, start: float, end: float, pattern: tuple[str, ...],
             floor: int, dyn: Dyn, div: int = 8, gate: float = 0.9, lag: float = 0.010,
             **kw) -> None:
    """Broken-chord figure: `pattern` names chord tones per subdivision (div per
    bar), cycling; the harmony map decides the tones bar by bar. Off-beats sit
    `lag` seconds late and each bar swells a little, so it plays rather than ticks."""
    step = 4.0 / div
    for bar, length, ch in sc.spans(start, end):
        tones = _tones(ch, floor)
        n = int(round(length * div))
        first = int(round((bar - int(bar)) * div))
        for k in range(n):
            idx = first + k
            vel = dyn.vel + dyn.accent[(idx * 8 // div) % 8] * (1.0 if div <= 8 else 0.7)
            if div == 16 and idx % 2:
                vel -= 6
            vel += 6.0 * (idx % div) / div - 3.0 + (2.0 if (int(bar) + idx // div) % 2 else 0.0)
            late = lag / sc.grid.spb_at(bar * 4) if (idx % (div // 4 or 1)) else 0.0
            sc.add(inst, bar * 4 + k * step + late, step * gate, tones[pattern[idx % len(pattern)]],
                   vel, **kw)


def block_chords(sc: Score, inst: str, start: float, end: float, lo: int, hi: int,
                 vel: int, rhythm: tuple[float, ...] = (0,), beats: float | None = None,
                 n: int = 3, roll: float = 0.0, prev: list[int] | None = None) -> list[int]:
    """Voiced chords struck at `rhythm` (beats within each harmony span)."""
    for bar, length, ch in sc.spans(start, end):
        prev = voice(ch, n, lo, hi, prev)
        for r in rhythm:
            if r < length * 4:
                sc.chord(inst, bar * 4 + r, beats or (length * 4 - r), prev, vel, roll=roll)
    return prev


def bass(sc: Score, start: float, end: float, vel: int, style: str = "eighths",
         inst: str = "cb_spic", sub: bool = True) -> None:
    """Root-based bass. eighths: driving repeated 8ths with a fifth pickup;
    pulse: beats 1 and 3 plus the '&' of 4; long: one note per chord."""
    for bar, length, ch in sc.spans(start, end):
        root = nearest(ch.bass, 38, 31, 45)
        fifth = root + 7 if root + 7 <= 47 else root - 5
        beats = length * 4
        b0 = bar * 4
        if sub:
            sc.add("sub", b0, beats - 0.1, root - 12, vel, jitter=0, vel_sd=0)
        if style == "long":
            sc.add(inst, b0, beats * 0.95, root, vel)
            continue
        if style == "pulse":
            hits = [(0, 1.5, root), (2, 1.5, root)] + ([(3.5, 0.5, fifth)] if beats >= 4 else [])
            for b, d, p in hits:
                if b < beats:
                    sc.add(inst, b0 + b, d, p, vel + (4 if b == 0 else 0))
            continue
        for k in range(int(beats * 2)):
            p = fifth if (k % 8 == 7 and beats >= 4) else root
            v = vel + (6 if k % 2 == 0 else -4) + (4 if k == 0 else 0)
            sc.add(inst, b0 + k * 0.5, 0.45, p, v)


def melody(sc: Score, inst: str, start: float, phrase: list[tuple], vel: int,
           octave: int = 0, legato: bool = False, clip: float | None = None,
           vel_curve: float = 0.0, **kw) -> None:
    """Render a phrase from `start` (bar). Sustained instruments get bow
    changes crossfaded when `legato`; `clip` (bars) drops notes past a point."""
    prev = None
    for b, d, p in phrase:
        if clip is not None and start + b / 4 >= clip:
            break
        tags = set()
        if legato and prev is not None and abs(prev[0] + prev[1] - b) < 1e-6:
            tags.add("legato")
            prev[2].tags.add("legato_out")
        v = vel + vel_curve * b + (4 if d >= 1.5 else 0)
        note = sc.add(inst, start * 4 + b, d * (0.98 if legato else 0.9), p + 12 * octave, v,
                      tags=tags, **kw)
        prev = (b, d, note)


def pad(sc: Score, start: float, end: float, vel: int, lo: int = 55, hi: int = 79,
        insts: tuple[str, ...] = ("vln_sus", "vla_sus", "vc_sus"), swell: float = 0.0) -> None:
    """Sustained string voicing per chord, split over the sections, kept quiet."""
    prev = None
    for bar, length, ch in sc.spans(start, end):
        prev = voice(ch, 4, lo, hi, prev)
        cello = nearest(ch.bass, 48, 43, 55)
        env = [(0.0, -swell), (length * 4 * 0.55 * sc.grid.spb_at(bar * 4), 0.0)] if swell else None
        for k, p in enumerate(sorted(prev)):
            inst = insts[0] if p >= 67 else insts[1]
            sc.add(inst, bar * 4, length * 4 * 0.98, p, vel - 2 * k, env=env)
        sc.add(insts[2], bar * 4, length * 4 * 0.98, cello, vel, env=env)


def soar(sc: Score, start: float, phrase: list[tuple], vel: int, clip: float | None = None) -> None:
    """Unison string line an octave apart: violins on top, violas and celli below."""
    melody(sc, "vln_sus", start, phrase, vel, octave=1, legato=True, clip=clip)
    melody(sc, "vla_sus", start, phrase, vel - 4, octave=0, legato=True, clip=clip)
    melody(sc, "vc_sus", start, phrase, vel - 8, octave=-1, legato=True, clip=clip)


def sparkle(sc: Score, start: float, end: float, vel: int, inst: str = "glock",
            floor: int = 86) -> None:
    """Two high chord tones on the '&' of 2 and beat 4: glints over the pulse."""
    for bar, length, ch in sc.spans(start, end):
        t = _tones(ch, floor)
        b0 = bar * 4
        for off, tone in ((1.5, "5"), (3.0, "9" if ch.root != 9 else "r8")):
            if off < length * 4:
                sc.add(inst, b0 + off, 1.0, t[tone], vel)


def flourish(sc: Score, inst: str, bar: float, vel: int, floor: int = 84,
             beat: float = 2.5, tones: tuple[str, ...] = ("9", "3", "5", "r8")) -> None:
    """Four rising sixteenths of chord tones under a held melody note."""
    t = _tones(sc.chord_at(bar + beat / 4), floor)
    for k, tone in enumerate(tones):
        sc.add(inst, bar * 4 + beat + 0.25 * k, 0.6, t[tone], vel + 3 * k)


def harp_run(sc: Score, at: float, ch: Chord, vel: int, up: bool = True, n: int = 8,
             beats: float = 1.0, floor: int = 50) -> None:
    """Arpeggiated run over `beats` ending on the downbeat at bar `at`."""
    pcs = sorted(ch.pcs)
    notes = []
    p = floor
    while len(notes) < n:
        p += 1
        if p % 12 in pcs:
            notes.append(p)
    if not up:
        notes.reverse()
    for k, p in enumerate(notes):
        sc.add("harp", at * 4 - beats + k * beats / n, 1.2, p, vel + k)
