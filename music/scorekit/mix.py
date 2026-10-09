"""Space and mastering: synthetic room and hall IRs, stem buses, loudness.

Moderately dry: a short room on everything that needs glue, a medium hall on
strings and horns only. Mid dips keep 1-4 kHz open for the narrator."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pyloudnorm as pyln
from pedalboard import HighpassFilter, HighShelfFilter, LowpassFilter, PeakFilter, Pedalboard
from scipy import signal
from scipy.ndimage import minimum_filter1d, uniform_filter1d

from .library import SR

HALL_RT = {63: 1.7, 125: 1.8, 250: 1.8, 500: 1.8, 1000: 1.7, 2000: 1.4, 4000: 1.1, 8000: 0.8,
           16000: 0.5}
ROOM_RT = {125: 0.45, 250: 0.5, 500: 0.5, 1000: 0.48, 2000: 0.42, 4000: 0.36, 8000: 0.3,
           16000: 0.22}


def _late_tail(n: int, rts: dict[int, float], rng: np.random.Generator) -> np.ndarray:
    t = np.arange(n) / SR
    out = np.zeros((n, 2))
    for fc, rt in rts.items():
        lo, hi = fc / np.sqrt(2), min(fc * np.sqrt(2), SR / 2 * 0.95)
        sos = signal.butter(2, [lo, hi], "band", fs=SR, output="sos")
        noise = signal.sosfiltfilt(sos, rng.standard_normal((n, 2)), axis=0)
        out += noise * np.exp(-6.9 * t / rt)[:, None]
    return out


def _normalise(ir: np.ndarray) -> np.ndarray:
    return ir / np.sqrt((ir ** 2).sum() / 2)


def hall_ir(rng: np.random.Generator, predelay: float = 0.018) -> np.ndarray:
    """Medium concert hall: sparse early reflections into a band-dependent tail."""
    n = int(2.6 * SR)
    ir = _late_tail(n, HALL_RT, rng)
    t = np.arange(n) / SR
    ir *= (1 - np.exp(-t / 0.03))[:, None]
    er = np.zeros((n, 2))
    for k in range(16):
        at = rng.uniform(0.005, 0.07)
        g = 0.5 * np.exp(-at / 0.05) * rng.uniform(0.5, 1.0)
        ch = k % 2
        er[int(at * SR), ch] += g
        er[int((at + rng.uniform(0.0005, 0.003)) * SR), 1 - ch] += g * 0.7
    er = signal.sosfilt(signal.butter(1, 6000, "low", fs=SR, output="sos"), er, axis=0)
    ir = _normalise(ir) + er * 0.9
    return _normalise(np.concatenate([np.zeros((int(predelay * SR), 2)), ir]))


def room_ir(rng: np.random.Generator) -> np.ndarray:
    """Small bright room: half a second, dense from the start."""
    n = int(0.7 * SR)
    ir = _late_tail(n, ROOM_RT, rng)
    t = np.arange(n) / SR
    ir *= (1 - np.exp(-t / 0.003))[:, None]
    return _normalise(np.concatenate([np.zeros((int(0.006 * SR), 2)), ir]))


def convolve(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    """True-ish stereo: each side feeds mostly its own IR channel."""
    x = signal.sosfilt(signal.butter(2, 180, "high", fs=SR, output="sos"), x, axis=0)
    a = 0.75 * x[:, 0] + 0.25 * x[:, 1]
    b = 0.25 * x[:, 0] + 0.75 * x[:, 1]
    wl = signal.oaconvolve(a, ir[:, 0])[: len(x)]
    wr = signal.oaconvolve(b, ir[:, 1])[: len(x)]
    return np.stack([wl, wr], axis=1)


@dataclass
class Bus:
    gain_db: float
    room: float                    # send level (linear, post-EQ)
    hall: float = 0.0
    eq: tuple = ()


def bus_settings() -> dict[str, Bus]:
    return {
        "piano": Bus(0.0, 0.16, 0.06, (HighpassFilter(40), PeakFilter(2600, -2.0, 0.8),
                                       PeakFilter(280, -2.0, 1.0), HighShelfFilter(8000, 1.0))),
        "strings": Bus(-1.0, 0.10, 0.30, (HighpassFilter(60), PeakFilter(2800, -3.0, 0.7),
                                          PeakFilter(320, -2.5, 1.0), LowpassFilter(14000))),
        "mallets": Bus(1.0, 0.18, 0.10, (HighpassFilter(80), PeakFilter(2500, -2.0, 0.8),
                                          HighShelfFilter(8000, -2.0))),
        "bass": Bus(5.0, 0.04, 0.0, (HighpassFilter(30), PeakFilter(75, 2.0, 1.0),
                                     LowpassFilter(5000))),
        "percussion": Bus(1.5, 0.14, 0.05, (HighpassFilter(35), PeakFilter(2600, -1.5, 0.8),
                                            HighShelfFilter(9000, -2.5))),
        "synth": Bus(-3.0, 0.10, 0.0, (HighpassFilter(28), PeakFilter(2600, -2.0, 0.8))),
        "winds": Bus(-4.0, 0.08, 0.28, (HighpassFilter(70), PeakFilter(2500, -3.0, 0.7),
                                        LowpassFilter(9000))),
    }


def automation_curve(points: list[tuple[float, float]], n: int) -> np.ndarray:
    if not points:
        return np.ones(n)
    pts = sorted(points)
    t = np.arange(n) / SR
    db = np.interp(t, [p[0] for p in pts], [p[1] for p in pts])
    return 10 ** (db / 20)


def process_stems(dry: dict[str, np.ndarray], automation: dict, seed: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    hall, room = hall_ir(rng), room_ir(rng)
    buses = bus_settings()
    out = {}
    for name, x in dry.items():
        bus = buses[name]
        x = x * automation_curve(automation.get(name, []), len(x))[:, None]
        board = Pedalboard(list(bus.eq))
        y = board(x.T.astype(np.float32), SR).T.astype(np.float64)
        wet = convolve(y, room) * bus.room
        if bus.hall:
            wet += convolve(y, hall) * bus.hall
        mixed = (y + wet) * 10 ** (bus.gain_db / 20)
        dc = signal.butter(2, 22, "high", fs=SR, output="sos")
        out[name] = signal.sosfiltfilt(dc, mixed, axis=0)
    return out


def true_peak_db(x: np.ndarray) -> float:
    up = signal.resample_poly(x, 4, 1, axis=0)
    return 20 * np.log10(np.abs(up).max() + 1e-12)


def _gain_envelope(mix: np.ndarray, ceiling_db: float, thresh_db: float, ratio: float) -> np.ndarray:
    """Linked gain: slow RMS compression plus a look-ahead peak limiter.

    One envelope for everything, so the stems still sum to the mix."""
    n = len(mix)
    mono_pow = (mix ** 2).mean(axis=1)
    w = int(0.4 * SR)
    rms_db = 10 * np.log10(uniform_filter1d(mono_pow, w, mode="nearest") + 1e-12)
    over = np.maximum(0.0, rms_db - thresh_db)
    comp_db = -over * (1 - 1 / ratio)
    comp = signal.sosfiltfilt(signal.butter(1, 1.5, "low", fs=SR, output="sos"), comp_db)
    g = 10 ** (comp / 20)
    peak = np.abs(signal.resample_poly(mix * g[:, None], 4, 1, axis=0)).max(axis=1)
    peak = peak.reshape(-1, 4).max(axis=1)[:n]
    need = np.minimum(1.0, 10 ** (ceiling_db / 20) / (peak + 1e-12))
    look = int(0.004 * SR)
    held = minimum_filter1d(need, 2 * look + 1, mode="nearest")
    smooth = uniform_filter1d(held, look, mode="nearest")
    released = signal.lfilter([1 - np.exp(-1 / (0.2 * SR))], [1, -np.exp(-1 / (0.2 * SR))],
                              smooth - 1.0) + 1.0
    lim = np.minimum(smooth, released)
    return g * np.minimum(lim, 1.0)


def master(stems: dict[str, np.ndarray], total: float, target_lufs: float = -16.0,
           tp_ceiling: float = -1.0, fade: float = 3.0) -> tuple[np.ndarray, dict, dict]:
    n = int(round(total * SR))
    stems = {k: v[:n] for k, v in stems.items()}
    fade_n = int(fade * SR)
    ramp = np.ones(n)
    ramp[-fade_n:] = np.cos(np.linspace(0, np.pi / 2, fade_n)) ** 2
    stems = {k: v * ramp[:, None] for k, v in stems.items()}
    mix = sum(stems.values())
    meter = pyln.Meter(SR)
    gain = 10 ** ((target_lufs - meter.integrated_loudness(mix)) / 20)
    env = np.ones(n)
    for _ in range(3):
        env = _gain_envelope(mix * gain, tp_ceiling - 0.3, target_lufs + 5.0, 1.6)
        lufs = meter.integrated_loudness(mix * gain * env[:, None])
        gain *= 10 ** ((target_lufs - lufs) / 20)
    env = _gain_envelope(mix * gain, tp_ceiling - 0.3, target_lufs + 5.0, 1.6) * gain
    stems = {k: v * env[:, None] for k, v in stems.items()}
    mix = mix * env[:, None]
    report = {"lufs_integrated": round(meter.integrated_loudness(mix), 2),
              "true_peak_dbtp": round(true_peak_db(mix), 2),
              "gain_applied_db": round(20 * np.log10(gain), 2),
              "max_gain_reduction_db": round(20 * np.log10(env.min() / gain), 2)}
    return mix, stems, report
