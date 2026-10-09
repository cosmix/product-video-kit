"""Quality control without ears: spectrograms, loudness curves, onset density,
a tempo estimate from the render, spectral centroid, click hunting."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from scipy import signal  # noqa: E402
from scipy.ndimage import maximum_filter1d, uniform_filter1d  # noqa: E402

from .library import SR  # noqa: E402
from .mix import true_peak_db  # noqa: E402

HOP = 0.01


def _k_weight(x: np.ndarray) -> np.ndarray:
    """ITU-R BS.1770 K-weighting at 48 kHz."""
    b1, a1 = [1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585]
    b2, a2 = [1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621]
    return signal.lfilter(b2, a2, signal.lfilter(b1, a1, x, axis=0), axis=0)


def loudness_curve(x: np.ndarray, win: float, hop: float = 0.1):
    k = _k_weight(x)
    p = (k ** 2).sum(axis=1)
    w, h = int(win * SR), int(hop * SR)
    c = np.cumsum(np.concatenate([[0.0], p]))
    idx = np.arange(0, len(p) - w, h)
    ms = (c[idx + w] - c[idx]) / w
    return (idx + w / 2) / SR, -0.691 + 10 * np.log10(ms + 1e-12)


def onset_strength(x: np.ndarray) -> np.ndarray:
    """Half-wave rectified log-spectral flux, one value per HOP seconds."""
    f, t, S = signal.spectrogram(x.mean(axis=1), SR, nperseg=2048, noverlap=2048 - int(HOP * SR))
    L = np.log10(S + 1e-10)
    flux = np.maximum(0.0, np.diff(L, axis=1)).mean(axis=0)
    return flux - uniform_filter1d(flux, int(0.5 / HOP), mode="nearest")


def onsets(x: np.ndarray) -> np.ndarray:
    """Onset times (s): local maxima of onset strength above an adaptive floor."""
    s = onset_strength(x)
    peaks = (s == maximum_filter1d(s, int(0.06 / HOP))) & (s > 0.6 * s.std())
    return np.where(peaks)[0] * HOP


def tempo_estimate(x: np.ndarray, lo: float = 70, hi: float = 200) -> float:
    """Autocorrelation of onset strength, peak between lo and hi BPM."""
    s = onset_strength(x)
    s = s - s.mean()
    ac = signal.correlate(s, s, mode="full")[len(s) - 1:]
    lags = np.arange(len(ac)) * HOP
    ok = (lags >= 60 / hi) & (lags <= 60 / lo)
    best = np.argmax(np.where(ok, ac, -np.inf))
    return float(60 / lags[best])


def centroid(x: np.ndarray) -> float:
    f, _, S = signal.spectrogram(x.mean(axis=1), SR, nperseg=4096)
    p = np.sqrt(S.mean(axis=1))
    return float((f * p).sum() / (p.sum() + 1e-12))


def section_stats(mix: np.ndarray, man: dict) -> list[dict]:
    ons = onsets(mix)
    out = []
    for s in man["sections"]:
        a, b = s["start"], s["end"]
        seg = mix[int(a * SR):int(b * SR)]
        k = _k_weight(seg)
        lufs = -0.691 + 10 * np.log10((k ** 2).sum(axis=1).mean() + 1e-12)
        out.append({"id": s["id"], "start": a, "onsets_per_s": round(float(((ons >= a) & (ons < b)).sum() / (b - a)), 2),
                    "centroid_hz": round(centroid(seg)), "lufs": round(float(lufs), 1)})
    return out


def clicks(x: np.ndarray, thresh: float = 12.0) -> list[float]:
    """Times where the >8 kHz residual spikes far above its local RMS."""
    sos = signal.butter(4, 8000, "high", fs=SR, output="sos")
    y = np.abs(signal.sosfilt(sos, x.mean(axis=1)))
    w = int(0.05 * SR)
    rms = np.sqrt(np.maximum(uniform_filter1d(y ** 2, w, mode="nearest"), 0.0)) + 1e-6
    hits = np.where((y / rms > thresh) & (y > 10 ** (-60 / 20)))[0]
    out, last = [], -SR
    for h in hits:
        if h - last > SR // 10:
            out.append(round(h / SR, 3))
        last = h
    return out


def _shade(ax, man):
    for a, b in man.get("speech_windows", []):
        ax.axvspan(a, b, color="#f2b25c", alpha=0.12, lw=0)
    for s in man["sections"]:
        ax.axvline(s["start"], color="#888888", lw=0.6, ls="--")
        ax.text(s["start"] + 0.2, ax.get_ylim()[1], s["id"], fontsize=7, va="top", color="#444")


def plots(out: Path, mix: np.ndarray, stems: dict[str, np.ndarray], man: dict) -> None:
    qc = out / "qc"
    fig, ax = plt.subplots(figsize=(18, 6))
    f, t, S = signal.spectrogram(mix.mean(axis=1), SR, nperseg=4096, noverlap=3072)
    ax.pcolormesh(t, f, 10 * np.log10(S + 1e-14), shading="auto", cmap="magma", vmin=-130, vmax=-50)
    ax.set_yscale("symlog", linthresh=200)
    ax.set_ylim(30, 16000)
    ax.set_title("soundtrack spectrogram")
    _shade(ax, man)
    fig.tight_layout()
    fig.savefig(qc / "spectrogram.png", dpi=90)
    plt.close(fig)

    fig, axes = plt.subplots(3, 1, figsize=(18, 11), sharex=True)
    tt, st = loudness_curve(mix, 3.0)
    tm, mm = loudness_curve(mix, 0.4)
    axes[0].plot(tm, mm, lw=0.6, label="momentary", color="#7fb1f0")
    axes[0].plot(tt, st, lw=1.4, label="short-term", color="#222")
    axes[0].set_ylim(-40, -5)
    axes[0].legend(loc="lower left")
    axes[0].set_title("loudness (LUFS)")
    _shade(axes[0], man)
    s = onset_strength(mix)
    axes[1].plot(np.arange(len(s)) * HOP, s, lw=0.5, color="#333")
    axes[1].set_title("onset strength")
    _shade(axes[1], man)
    for name, x in stems.items():
        _, lb = loudness_curve(x, 1.0)
        axes[2].plot(np.arange(len(lb)) * 0.1 + 0.5, lb, lw=0.9, label=name)
    axes[2].set_ylim(-60, -10)
    axes[2].set_title("stem loudness (LUFS, 1 s)")
    axes[2].legend(loc="lower left", ncol=7)
    _shade(axes[2], man)
    fig.tight_layout()
    fig.savefig(qc / "loudness.png", dpi=90)
    plt.close(fig)


def run_qc(out: Path, man: dict) -> dict:
    (out / "qc").mkdir(parents=True, exist_ok=True)
    mix, _ = sf.read(out / "soundtrack.wav", always_2d=True)
    stems = {k: sf.read(out.parent / v, always_2d=True)[0] for k, v in man["stems"].items()}
    plots(out, mix, stems, man)
    report = {"mix": {"true_peak_dbtp": round(true_peak_db(mix), 2),
                      "sample_peak_db": round(20 * np.log10(np.abs(mix).max()), 2),
                      "duration_s": round(len(mix) / SR, 3),
                      "tempo_estimate_bpm": round(tempo_estimate(mix), 2),
                      "clicks": clicks(mix)[:20],
                      "tail_last_100ms_db": round(20 * np.log10(np.abs(mix[-SR // 10:]).max() + 1e-12), 1)},
              "sections": section_stats(mix, man)}
    total = sum(stems.values())
    report["stems_sum_error_db"] = round(20 * np.log10(np.abs(total - mix).max() + 1e-12), 1)
    report["stem_clicks"] = {name: clicks(x)[:8] for name, x in stems.items()}
    return report
