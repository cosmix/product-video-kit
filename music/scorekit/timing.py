"""The tempo and bar grid a cue sits on, built from the project's numbers.

    grid = Grid(bpm=120.0, bar0_at=1.5, total=180.0,
                local=[(51.5, 11.5, 23.53)],            # bars 51.5-63 span exactly 23.53 s
                sections=[("intro", 0, 0.0), ("pitch", 13, 27.9), ...])

Bars are addressed as floats: bar 51.5 is beat 3 of bar 51. `local` passages run at their own
tempo so a fixed stretch of picture holds a whole number of (half) bars; everything after keeps
the base tempo. `sections` are (id, first bar, picture cut in seconds); `speech` defaults to the
narration windows in narration/timeline.json (for QC shading).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

TIMELINE = Path(__file__).resolve().parents[2] / "narration" / "timeline.json"


@dataclass(frozen=True)
class Section:
    id: str
    bar: float          # first bar (float: .5 = beat 3)
    end: float          # exclusive
    scene: float        # picture cut, seconds


def narration_windows() -> list[tuple[float, float]]:
    if not TIMELINE.exists():
        return []
    return [(s["start"], s["end"]) for s in json.loads(TIMELINE.read_text())["narration"]]


class Grid:
    def __init__(self, bpm: float, bar0_at: float, total: float, local=(), sections=(), speech=None):
        self.bpm, self.offset, self.total = bpm, bar0_at, total
        self.spb = 60.0 / bpm
        # tempo map: (first beat, seconds at that beat, seconds per beat)
        self.segments = [(0.0, bar0_at, self.spb)]
        for first_bar, bars, seconds in sorted(local):
            t0 = self.beat_t(first_bar * 4)
            self.segments.append((first_bar * 4, t0, seconds / (bars * 4)))
            self.segments.append(((first_bar + bars) * 4, t0 + seconds, self.spb))
        self.end_bar = self.bars_at(total)
        bars = [b for _, b, _ in sections] + [self.end_bar]
        self.sections = [Section(i, b, bars[k + 1], s) for k, (i, b, s) in enumerate(sections)]
        self.speech = narration_windows() if speech is None else list(speech)

    def _segment(self, beat: float) -> tuple[float, float, float]:
        for seg in reversed(self.segments):
            if beat >= seg[0]:
                return seg
        return self.segments[0]

    def beat_t(self, beat: float) -> float:
        """Seconds at an absolute beat count from bar 0."""
        b0, t0, spb = self._segment(beat)
        return t0 + (beat - b0) * spb

    def spb_at(self, beat: float) -> float:
        """Seconds per beat in force at an absolute beat."""
        return self._segment(beat)[2]

    def t(self, bar: float) -> float:
        """Seconds at a (fractional) bar number."""
        return self.beat_t(bar * 4)

    def bars_at(self, seconds: float) -> float:
        """Fractional bar number at a time."""
        for b0, t0, spb in reversed(self.segments):
            if seconds >= t0:
                return (b0 + (seconds - t0) / spb) / 4
        return (seconds - self.offset) / (4 * self.spb)

    def manifest(self) -> dict:
        n_bars = int(self.end_bar) + 1
        return {
            "sample_rate": 48000,
            "duration": self.total,
            "bpm": self.bpm,
            "time_signature": "4/4",
            "bar_0_at": self.offset,
            "bar_length": round(4 * self.spb, 5),
            "tempo_map": [{"bar": b0 / 4, "bpm": round(60.0 / spb, 3), "at": round(t0, 4)}
                          for b0, t0, spb in self.segments],
            "downbeats": [round(self.t(b), 4) for b in range(n_bars)],
            "beats": [round(self.beat_t(b), 4) for b in range(4 * n_bars)],
            "sections": [{"id": s.id, "bar": s.bar, "start": round(self.t(s.bar), 4),
                          "end": round(self.t(s.end), 4), "scene_cut": s.scene,
                          "offset_from_cut": round(self.t(s.bar) - s.scene, 3)} for s in self.sections],
            "speech_windows": self.speech,
        }
