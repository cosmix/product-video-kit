"""Sample playback: repitch, envelope, sustain extension, stereo placement."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import soxr
from scipy import signal
from scipy.ndimage import uniform_filter1d

from .instruments import Instrument
from .library import SR, Zone, load


@dataclass
class Note:
    t: float                        # onset, seconds
    dur: float                      # key-down length (piano: until damper)
    pitch: float                    # MIDI
    vel: int
    inst: str
    env: list[tuple[float, float]] | None = None   # (seconds from onset, dB)
    pan: float | None = None
    gain_db: float = 0.0
    rr: int = 0
    tags: set[str] = field(default_factory=set)


@lru_cache(maxsize=None)
def sustain_end(path) -> int:
    """Sample index where the recorded sustain starts to die away."""
    x = load(path).mean(axis=1)
    hop = int(0.05 * SR)
    rms = np.sqrt(uniform_filter1d(x ** 2, hop, mode="nearest")[::hop] + 1e-12)
    mid = rms[len(rms) // 5: 3 * len(rms) // 5]
    ref = np.median(mid) if len(mid) else rms.max()
    alive = np.where(rms > ref * 10 ** (-7 / 20))[0]
    return int(alive[-1] * hop) if len(alive) else len(x)


def _extend(x: np.ndarray, need: int, end: int, rng: np.random.Generator) -> np.ndarray:
    """Crossfade-loop the sustained body of x until it is `need` samples long."""
    xf = int(0.45 * SR)
    body_lo = int(1.2 * SR)
    if end - body_lo < 2 * xf + SR // 2:
        body_lo = max(int(0.4 * SR), end - 2 * xf - SR)
    out = x[:end].copy()
    fade_in = np.sin(np.linspace(0, np.pi / 2, xf))[:, None] ** 2
    fade_out = 1.0 - fade_in
    while len(out) < need:
        seg_len = min(end - body_lo, int(rng.uniform(2.0, 3.5) * SR))
        start = int(rng.uniform(body_lo, max(body_lo + 1, end - seg_len)))
        seg = x[start:start + seg_len]
        tail = out[-xf:] * fade_out + seg[:xf] * fade_in
        out = np.concatenate([out[:-xf], tail, seg[xf:]])
    return out


def _stereo(x: np.ndarray, pan: float, width: float) -> np.ndarray:
    mid = 0.5 * (x[:, 0] + x[:, 1])
    side = 0.5 * (x[:, 0] - x[:, 1]) * width
    ang = (pan + 1.0) * np.pi / 4.0
    return np.stack([(mid + side) * np.cos(ang) * np.sqrt(2),
                     (mid - side) * np.sin(ang) * np.sqrt(2)], axis=1)


def _breath(t: np.ndarray, dur: float, inst: Instrument, rng: np.random.Generator) -> np.ndarray:
    """Bow/breath phrasing for sustained notes: a gentle arc plus slow drift (dB)."""
    rise, fall = inst.extra.get("arc", (2.5, 2.0))
    peak = dur * rng.uniform(0.3, 0.45)
    arc = np.interp(t, [0.0, peak, max(dur, peak + 0.01)], [-rise, 0.0, -fall])
    rate = rng.uniform(0.2, 0.4)
    drift = 0.7 * np.sin(2 * np.pi * rate * t + rng.uniform(0, 2 * np.pi))
    return arc + drift


def _env_curve(n: int, note: Note, inst: Instrument, held: int, rel_s: float,
               attack_s: float, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(n) / SR - inst.pre_roll
    g = np.ones(n)
    att = max(1, int(attack_s * SR))
    g[:att] *= np.sin(np.linspace(0, np.pi / 2, att)) ** 2
    if inst.kind == "sustain":
        g *= 10 ** (_breath(t, note.dur, inst, rng) / 20)
    if note.env:
        pts = sorted(note.env)
        ts = np.array([p[0] for p in pts])
        db = np.array([p[1] for p in pts])
        g *= 10 ** (np.interp(t, ts, db) / 20)
    if n > held:
        tail = np.arange(n - held) / SR
        decay = np.exp(-tail / (max(rel_s, 0.02) / 4.0))
        decay *= np.cos(np.linspace(0, np.pi / 2, len(tail))) ** 0.5
        g[held:] *= decay
    return g


def render_note(note: Note, inst: Instrument, rng: np.random.Generator) -> tuple[int, np.ndarray]:
    """Render one note; returns (start sample, stereo block).

    Legato pairs: the incoming note skips its bow attack and fades in while the
    outgoing note releases quickly, a crossfaded bow change."""
    rel_s = inst.release
    if inst.kind == "piano" and note.pitch >= 89:
        rel_s = 3.0
    if "legato_out" in note.tags:
        rel_s = min(rel_s, 0.2)
    legato_in = "legato" in note.tags and inst.kind == "sustain"
    offset = 0.07 if legato_in else 0.0
    attack = 0.06 if legato_in else inst.attack
    total_s = note.dur + rel_s
    detune = rng.normal(0, inst.detune_cents) / 100.0 if inst.detune_cents else 0.0
    out = None
    for zone, weight in inst.pick(note.pitch, note.vel, note.rr):
        if weight <= 1e-3:
            continue
        block = _render_zone(zone, note.pitch + detune, total_s, inst, rng, offset)
        block *= weight
        if out is None:
            out = block
        else:
            n = min(len(out), len(block))
            out = out[:n] + block[:n]
    if out is None:
        return 0, np.zeros((1, 2))
    held = min(len(out), int((note.dur + inst.pre_roll) * SR))
    n = len(out)
    g = _env_curve(n, note, inst, held, rel_s, attack, rng)
    v = note.vel / 127.0
    vel_gain = (1 - inst.veltrack) + inst.veltrack * v * v
    out *= (g * vel_gain * 10 ** ((inst.gain_db + note.gain_db) / 20))[:, None]
    pan = inst.pan if note.pan is None else note.pan
    out = _stereo(out, pan, inst.width)
    start = int(round((note.t - inst.pre_roll) * SR))
    if start < 0:
        out = out[-start:]
        start = 0
    return start, out.astype(np.float32)


def _render_zone(zone: Zone, pitch: float, total_s: float, inst: Instrument,
                 rng: np.random.Generator, offset_s: float = 0.0) -> np.ndarray:
    x = load(zone.path)
    ratio = 2.0 ** ((pitch - zone.pitch) / 12.0)
    skip = int(offset_s * SR * ratio)
    x = x[skip:]
    need_out = int((total_s + inst.pre_roll) * SR) + 1
    need_in = int(need_out * ratio) + 64
    if inst.kind == "sustain":
        end = sustain_end(zone.path) - skip
        if need_in > end - int(0.3 * SR):
            x = _extend(x, need_in, end, rng)
    x = x[:need_in]
    if abs(ratio - 1.0) > 1e-6:
        y = soxr.resample(x, SR * ratio, SR, quality="HQ")
    else:
        y = x.copy()
    y = y[:need_out].astype(np.float64)
    if len(y) < need_out:
        tail = min(len(y), int(0.01 * SR))
        if tail:
            y[-tail:] *= np.linspace(1, 0, tail)[:, None]
    return y


@lru_cache(maxsize=None)
def _filters(lowpass: float | None, highpass: float | None):
    sos = []
    if lowpass:
        sos.append(signal.butter(2, lowpass, "low", fs=SR, output="sos"))
    if highpass:
        sos.append(signal.butter(2, highpass, "high", fs=SR, output="sos"))
    return np.concatenate(sos) if sos else None


def render_part(notes: list[Note], inst: Instrument, length: int, seed: int) -> np.ndarray:
    """Render all notes of one instrument into a stereo buffer of `length` samples."""
    rng = np.random.default_rng(seed)
    buf = np.zeros((length, 2), dtype=np.float64)
    counters: dict[int, int] = {}
    for note in sorted(notes, key=lambda n: n.t):
        key = int(round(note.pitch))
        note.rr = counters.get(key, 0)
        counters[key] = note.rr + 1
        start, block = render_note(note, inst, rng)
        end = min(length, start + len(block))
        if end > start:
            buf[start:end] += block[: end - start]
    sos = _filters(inst.lowpass, inst.highpass)
    if sos is not None:
        buf = signal.sosfilt(sos, buf, axis=0)
    return buf
