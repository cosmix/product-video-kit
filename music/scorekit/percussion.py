"""Percussion: VSCO one-shots (orchestral bass drum, snare, shaker, tambourine,
tenor drums, large frame drum, cymbals, triangle, wind chimes) and synthesized
modern pieces (kick, clap, snap, riser). No brushes, no swing."""

from __future__ import annotations

import numpy as np
from scipy import signal

from . import synth
from .library import SR, VSCO, load
from .sampler import Note, _stereo

P1 = VSCO / "VSCO 1 Percussion"
_TENOR_LO = P1 / "drums/tenor/tenor_lower"
_TENOR_HI = P1 / "drums/tenor/tenor_higher"
_GIANT = P1 / "drums/other/ethnic/giant/mallet"
_SUSP = P1 / "varMetal/Cymbals/susp"

# name -> (velocity layers, each a list of round-robin files; pan; lowpass Hz; decay s)
KIT = {
    "bdrum": ([[P1 / "drums/bass" / f"bdrum_muted_pp_{i}.wav" for i in (1, 2, 3)],
               [P1 / "drums/bass" / f"bdrum_muted_mp_{i}.wav" for i in (1, 2)],
               [P1 / "drums/bass/bdrum_muted_mf_1.wav"]], 0.0, 400.0, 0.5),
    "snare": ([[P1 / "drums/snare/drum2" / f"snare2_p_{i}.wav" for i in (1, 2, 3)],
               [P1 / "drums/snare/drum2" / f"snare2_mf_{i}.wav" for i in (1, 2)]], 0.05, 9000.0, 0.3),
    "click": ([[P1 / "drums/snare/drum1" / n for n in
                ("snare1_click.wav", "snare1_click2.wav", "snare1_click3.wav", "snare1_click4.wav")]],
              -0.15, 8000.0, 0.2),
    "shaker": ([[P1 / "varWood/Camo's Shaker" / f"shake{i}.wav" for i in range(1, 9)]],
               0.35, 8000.0, 0.15),
    "tamb": ([[P1 / "varWood" / f"tambourine_up_{i}.wav" for i in (2, 3, 4, 6)],
              [P1 / "varWood" / f"tambourine_down_{i}.wav" for i in (2, 3, 4, 6)]], -0.3, 8500.0, 0.3),
    "tom_lo": ([[_TENOR_LO / f"tenor_pp_{i}.wav" for i in (1, 2, 3, 4)],
                [_TENOR_LO / f"tenor_mf_{i}.wav" for i in (1, 2, 3, 4)],
                [_TENOR_LO / f"tenor_ff_{i}.wav" for i in (1, 2, 3)]], -0.25, 5000.0, 0.6),
    "tom_hi": ([[_TENOR_HI / f"tenorH_p_{i}.wav" for i in (1, 2, 3)],
                [_TENOR_HI / f"tenorH_mf_{i}.wav" for i in (1, 2, 3)],
                [_TENOR_HI / f"tenorH_ff_{i}.wav" for i in (1, 2, 3, 4)]], 0.3, 5000.0, 0.6),
    "taiko": ([[_GIANT / "EthnicLargeMallet_hit_pp_1.wav"], [_GIANT / "EthnicLargeMallet_hit_mf_1.wav"],
               [_GIANT / f"EthnicLargeMallet_hit_ff_{i}.wav" for i in (1, 2)]], 0.0, 3000.0, 0.8),
    "cym_hit": ([[_SUSP / "susp_hit_softmall_p.wav"], [_SUSP / "susp_hit_softmall_mp.wav"],
                 [_SUSP / "susp_hit_softmall_f.wav"]], 0.2, 12000.0, 2.5),
    "triangle": ([[VSCO / "Percussion/temp" / f"Triangle3-Hit_v1_rr{i}_Sum.wav" for i in (1, 2)]],
                 0.45, None, 2.0),
    "fingcymb": ([[P1 / "varMetal/various/Fing_Cymb.wav"]], 0.5, None, 2.0),
}
# swells anchored at their loudest point: file, seconds from file start to the peak
SWELLS = {
    "cym_swell": (_SUSP / "susp_hit_softmall_roll2_cresc.wav", 3.84),
    "cym_swell_short": (_SUSP / "susp_hit_softmall_roll1.wav", 1.81),
    "chimes": (P1 / "varMetal/various/windchimes_asc1.wav", 1.59),
}


def _shape(x: np.ndarray, dur: float, decay: float) -> np.ndarray:
    """Hold for `dur`, then fade out over `decay` seconds."""
    hold = int(dur * SR)
    n = min(len(x), hold + int(decay * SR))
    x = x[:n].copy()
    if n > hold:
        x[hold:] *= np.cos(np.linspace(0, np.pi / 2, n - hold))[:, None] ** 2
    return x


def _swell(note: Note) -> tuple[np.ndarray, int]:
    """A crescendo sample placed so its peak lands on the note time; the part
    before the peak is lifted from the start of the file when needed."""
    path, peak_at = SWELLS[note.inst]
    x = load(path).astype(np.float64)
    lead = min(note.dur, peak_at)                       # seconds of swell before the hit
    start = int((peak_at - lead) * SR)
    x = x[start:]
    fade = int(min(lead, 0.6) * SR)
    if fade:
        x[:fade] *= np.linspace(0, 1, fade)[:, None] ** 2
    return _shape(x, lead, 2.5), int(round((note.t - lead) * SR))


def _sampled(note: Note, rng: np.random.Generator) -> tuple[np.ndarray, float]:
    layers, dflt_pan, lp, decay = KIT[note.inst]
    layer = layers[min(len(layers) - 1, int(note.vel / 128 * len(layers)))]
    x = load(layer[note.rr % len(layer)]).astype(np.float64)
    if lp:
        x = signal.sosfilt(signal.butter(2, lp, "low", fs=SR, output="sos"), x, axis=0)
    return _shape(x, note.dur, decay), dflt_pan


def render_hit(note: Note, rng: np.random.Generator) -> tuple[int, np.ndarray]:
    kind, start = note.inst, int(round(note.t * SR))
    pan = note.pan
    if kind == "kick":
        x, dflt = synth.kick(note.vel), 0.0
    elif kind == "clap":
        x, dflt = synth.clap(note.vel, rng), 0.1
    elif kind == "snap":
        x, dflt = synth.snap(note.vel, rng), -0.2
    elif kind == "sub_drop":
        x, dflt = synth.sub_drop(note.vel), 0.0
    elif kind == "riser":
        x, dflt = synth.riser(note.dur, note.vel, rng), 0.0
        start = int(round((note.t - note.dur) * SR))
    elif kind in SWELLS:
        x, start = _swell(note)
        dflt = 0.25
    else:
        x, dflt = _sampled(note, rng)
    v = note.vel / 127.0
    x = x * (0.25 + 0.75 * v * v) * 10 ** (note.gain_db / 20)
    if note.env:
        tt = np.arange(len(x)) / SR
        pts = sorted(note.env)
        x *= 10 ** (np.interp(tt, [p[0] for p in pts], [p[1] for p in pts]) / 20)[:, None]
    return start, _stereo(x, dflt if pan is None else pan, 0.6)


def render_percussion(notes: list[Note], length: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    buf = np.zeros((length, 2))
    counters: dict[str, int] = {}
    for note in sorted(notes, key=lambda n: n.t):
        prev = counters.get(note.inst, -1)
        note.rr = int(rng.integers(0, 8)) if note.inst in ("shaker", "click") else prev + 1
        if note.rr == prev:
            note.rr += 1
        counters[note.inst] = note.rr
        start, x = render_hit(note, rng)
        if start < 0:
            x, start = x[-start:], 0
        end = min(length, start + len(x))
        if end > start:
            buf[start:end] += x[: end - start]
    return buf


PERC = set(KIT) | set(SWELLS) | {"kick", "clap", "snap", "riser", "sub_drop"}
