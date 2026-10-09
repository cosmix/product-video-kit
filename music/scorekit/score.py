"""Score container: notes placed on the bar grid, humanised, plus stem automation and the
harmony map the textures in parts.py read.

    sc = Score(grid, harmony=[(0, 2, "C"), (2, 2, "Am7"), (4, 1, "F"), (5, 1, "G")], seed=7)

`harmony` lists (first bar, length in bars, chord symbol); half bars are fine."""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from .sampler import Note
from .theory import Chord, chord
from .timing import Grid

# timing spread (seconds, 1 sd) per instrument; the pulse instruments stay tight
JITTER = {"piano": 0.007, "marimba": 0.007, "glock": 0.008, "xylo": 0.006, "harp": 0.009,
          "vln_spic": 0.013, "vla_spic": 0.013, "vc_spic": 0.012, "cb_spic": 0.010,
          "vln_pizz": 0.012, "vla_pizz": 0.012, "vc_pizz": 0.011, "cb_pizz": 0.009,
          "vln_sus": 0.014, "vla_sus": 0.014, "vc_sus": 0.014, "horn": 0.012,
          "pluck": 0.0, "sub": 0.0}
# systematic placement against the grid (seconds): sampled attacks sit a hair late
LAG = {"vln_sus": -0.03, "vla_sus": -0.03, "vc_sus": -0.03, "horn": -0.02}


class Score:
    def __init__(self, grid: Grid, harmony=(), seed: int = 7):
        self.grid = grid
        self.harmony = list(harmony)
        self.notes: dict[str, list[Note]] = defaultdict(list)
        self.automation: dict[str, list[tuple[float, float]]] = defaultdict(list)
        self.rng = np.random.default_rng(seed)

    def auto(self, stem: str, bar: float, db: float) -> None:
        """Stem gain breakpoint (dB) at a bar; linear in dB between points."""
        self.automation[stem].append((self.grid.beat_t(bar * 4), db))

    def add(self, inst: str, beat: float, beats: float, pitch: float, vel: float,
            env=None, jitter: float | None = None, vel_sd: float = 5.0, **kw) -> Note:
        """Place one note. `beat` is absolute (bar * 4 + beat-in-bar)."""
        t = self.grid.beat_t(beat)
        sd = JITTER.get(inst, 0.005) if jitter is None else jitter
        if sd:
            t += float(np.clip(self.rng.normal(0, sd), -2.5 * sd, 2.5 * sd))
        t += LAG.get(inst, 0.0)
        v = int(np.clip(vel + (self.rng.normal(0, vel_sd) if vel_sd else 0), 1, 127))
        if vel_sd and inst not in ("pluck", "sub"):
            kw["gain_db"] = kw.get("gain_db", 0.0) + float(self.rng.normal(0, 0.7))
        note = Note(max(0.0, t), max(0.03, beats * self.grid.spb_at(beat)), pitch, v, inst, env, **kw)
        self.notes[inst].append(note)
        return note

    def hit(self, kind: str, beat: float, vel: float, beats: float = 0.25,
            jitter: float = 0.003, **kw) -> Note:
        """Percussion one-shot; `kind` names a kit piece in percussion.py."""
        return self.add(kind, beat, beats, 60, vel, jitter=jitter, **kw)

    def chord(self, inst: str, beat: float, beats: float, pitches: list[int], vel: float,
              roll: float = 0.0, **kw) -> None:
        """Simultaneous notes, optionally rolled bottom-up by `roll` beats in total."""
        for k, p in enumerate(sorted(pitches)):
            off = roll * k / max(1, len(pitches) - 1) if roll else 0.0
            self.add(inst, beat + off, beats - off, p, vel, **kw)

    def chord_at(self, bar: float) -> Chord:
        for start, length, sym in self.harmony:
            if start <= bar < start + length:
                return chord(sym)
        raise ValueError(f"no chord at bar {bar} in the harmony map")

    def spans(self, start: float, end: float) -> list[tuple[float, float, Chord]]:
        """Harmony entries overlapping [start, end), clipped: (bar, length, chord)."""
        out = []
        for s, length, sym in self.harmony:
            a, b = max(s, start), min(s + length, end)
            if b > a:
                out.append((a, b - a, chord(sym)))
        return out
