"""Small synthesized voices: a soft pluck, a sub bass, a modern kick, claps,
snaps and noise risers. All return stereo float64 blocks at SR."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy import signal

from .library import SR


def _hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


@lru_cache(maxsize=None)
def _lp(fc: float, order: int = 2):
    return signal.butter(order, min(fc, SR * 0.45), "low", fs=SR, output="sos")


@lru_cache(maxsize=None)
def _bp(lo: float, hi: float, order: int = 2):
    return signal.butter(order, [lo, min(hi, SR * 0.45)], "band", fs=SR, output="sos")


def _sweep_lp(x: np.ndarray, fc: np.ndarray, step: int) -> np.ndarray:
    """Time-varying 2nd-order lowpass, coefficients updated every `step` samples,
    filter state carried across blocks so nothing clicks."""
    out = np.zeros(len(x))
    zi = np.zeros((1, 2))
    for i in range(0, len(x), step):
        sos = _lp(float(round(fc[i], -1)))
        out[i:i + step], zi = signal.sosfilt(sos, x[i:i + step], zi=zi)
    return out


def _sweep_bp(x: np.ndarray, fc: np.ndarray, step: int) -> np.ndarray:
    out = np.zeros(len(x))
    zi = np.zeros((2, 2))
    for i in range(0, len(x), step):
        f = float(round(fc[i], -1))
        out[i:i + step], zi = signal.sosfilt(_bp(f * 0.6, f * 1.6), x[i:i + step], zi=zi)
    return out


def _saw(f: float, n: int, phase: float = 0.0) -> np.ndarray:
    """Band-limited-enough sawtooth: sum of harmonics below 14 kHz."""
    t = np.arange(n) / SR
    out = np.zeros(n)
    for k in range(1, int(14000 / f) + 1):
        out += np.sin(2 * np.pi * k * f * t + phase * k) / k
    return out * (2 / np.pi)


def pluck(midi: float, dur: float, vel: int, rng: np.random.Generator) -> np.ndarray:
    """Two detuned saws through a fast-closing lowpass; a warm synth pluck."""
    n = int((dur + 0.6) * SR)
    f = _hz(midi)
    x = _saw(f * 2 ** (-4 / 1200), n, rng.uniform(0, 6)) + _saw(f * 2 ** (4 / 1200), n, rng.uniform(0, 6))
    t = np.arange(n) / SR
    amp = np.exp(-t / 0.35) * (1 - np.exp(-t / 0.002))
    amp[int(dur * SR):] *= np.exp(-(t[int(dur * SR):] - dur) / 0.08)
    bright = 500 + 1900 * (vel / 127) * np.exp(-t / 0.12)
    out = _sweep_lp(x, bright, 256)
    out *= amp * 0.26 * (0.4 + 0.6 * vel / 127)
    return np.stack([out, out * 0.92], axis=1)


def sub(midi: float, dur: float, vel: int) -> np.ndarray:
    """Sine sub with a soft attack and a rounded release, tracking the bass."""
    n = int((dur + 0.25) * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * _hz(midi) * t)
    env = (1 - np.exp(-t / 0.012)) * np.ones(n)
    rel = t > dur
    env[rel] *= np.exp(-(t[rel] - dur) / 0.06)
    x *= env * 0.13 * (0.5 + 0.5 * vel / 127)
    return np.stack([x, x], axis=1)


def sub_drop(vel: int) -> np.ndarray:
    """Downbeat impact: a sine falling 90 -> 32 Hz over 0.7 s."""
    n = int(1.1 * SR)
    t = np.arange(n) / SR
    f = 32 + 58 * np.exp(-t / 0.22)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.35) * (1 - np.exp(-t / 0.01))
    x *= 0.5 * (0.4 + 0.6 * vel / 127)
    return np.stack([x, x], axis=1)


def kick(vel: int) -> np.ndarray:
    """Soft modern kick: sine sweep 110 -> 48 Hz with a short click."""
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 48 + 62 * np.exp(-t / 0.04)
    phase = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(phase) * np.exp(-t / 0.13)
    click = signal.sosfilt(_bp(800, 4000), np.random.default_rng(3).standard_normal(n)) \
        * np.exp(-t / 0.004) * 0.12
    x = (body + click) * (0.45 + 0.55 * vel / 127) * 0.9
    return np.stack([x, x], axis=1)


def clap(vel: int, rng: np.random.Generator) -> np.ndarray:
    """Group clap: four staggered noise bursts into a 120 ms room."""
    n = int(0.4 * SR)
    t = np.arange(n) / SR
    noise = signal.sosfilt(_bp(900, 5200), rng.standard_normal(n))
    env = np.zeros(n)
    for k in range(4):
        at = int((0.007 * k + rng.uniform(0, 0.002)) * SR)
        env[at:] += np.exp(-(t[at:] - t[at]) / 0.009) * (0.9 if k < 3 else 0.6)
    env += 0.55 * np.exp(-(t - 0.024) / 0.12) * (t > 0.024)
    x = noise * env * 0.30 * (0.4 + 0.6 * vel / 127)
    x = signal.sosfilt(_lp(9000), x)
    other = signal.sosfilt(_bp(1200, 6000), rng.standard_normal(n)) * env * 0.05
    return np.stack([x + other, x - other], axis=1)


def snap(vel: int, rng: np.random.Generator) -> np.ndarray:
    """Finger snap: one bright burst plus a tiny tuned thump."""
    n = int(0.18 * SR)
    t = np.arange(n) / SR
    burst = signal.sosfilt(_bp(1800, 7000), rng.standard_normal(n)) * np.exp(-t / 0.012)
    thump = np.sin(2 * np.pi * 420 * t) * np.exp(-t / 0.02) * 0.5
    x = (burst * 0.35 + thump) * 0.4 * (0.4 + 0.6 * vel / 127)
    return np.stack([x, x * 0.9], axis=1)


def riser(dur: float, vel: int, rng: np.random.Generator) -> np.ndarray:
    """Filtered-noise riser: cutoff and level climb to the downbeat, then stop."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    u = t / dur
    noise = rng.standard_normal(n)
    out = _sweep_bp(noise, 250 + 4200 * u ** 2, 512)
    env = u ** 2.2 * (1 - np.exp(-t / 0.05))
    x = out * env * 0.055 * (0.4 + 0.6 * vel / 127)
    x[-int(0.01 * SR):] *= np.linspace(1, 0, int(0.01 * SR))
    width = signal.sosfilt(_bp(2000, 8000), rng.standard_normal(n)) * env * 0.03
    return np.stack([x + width, x - width], axis=1)
