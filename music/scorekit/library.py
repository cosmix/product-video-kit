"""Sample-library indexing: Salamander Grand Piano (sfz) and VSCO-2 CE folders.

Every instrument becomes a list of Zones. A zone is one recorded sample with the
MIDI pitch it sounds at, the velocity band it covers and a round-robin index.
VSCO file names use an octave convention that differs between folders, so each
folder's octave offset is measured once by pitch detection and cached.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr

SR = 48000
ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
SALAMANDER = SAMPLES / "SalamanderGrandPianoV3_48khz24bit"
VSCO = SAMPLES / "VSCO-2-CE-master"
CACHE = ROOT / "build" / "octave_offsets.json"
TUNE_CACHE = ROOT / "build" / "fine_tune.json"

NOTE_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def note_to_midi(name: str) -> int:
    m = re.fullmatch(r"([A-G])([#b]?)(-?\d)", name)
    if not m:
        raise ValueError(f"bad note name {name!r}")
    pc = NOTE_PC[m.group(1)] + {"#": 1, "b": -1, "": 0}[m.group(2)]
    return pc + 12 * (int(m.group(3)) + 1)


@dataclass(frozen=True)
class Zone:
    path: Path
    pitch: float          # sounding MIDI pitch incl. tuning correction
    lovel: int
    hivel: int
    layer: int            # dynamic layer index, 0 = softest
    rr: int = 0
    lokey: int = 0
    hikey: int = 127


@lru_cache(maxsize=None)
def load(path: Path) -> np.ndarray:
    """Load a sample as float32 stereo at SR, leading silence trimmed."""
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    data = data[:, :2]
    if sr != SR:
        data = soxr.resample(data, sr, SR, quality="VHQ").astype(np.float32)
    env = np.abs(data).max(axis=1)
    thresh = env.max() * 10 ** (-48 / 20)
    idx = int(np.argmax(env > thresh))
    start = max(0, idx - int(0.002 * SR))
    out = data[start:].copy()
    fade = min(len(out), int(0.001 * SR))
    out[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)[:, None]
    return out


def salamander() -> list[Zone]:
    sfz = (SALAMANDER / "SalamanderGrandPianoV3Retuned.sfz").read_text()
    zones: list[Zone] = []
    for line in sfz.splitlines():
        if not line.startswith("<region>"):
            continue
        ops = dict(re.findall(r"(\w+)=(\S+)", line))
        name = ops["sample"].split("\\")[-1]
        m = re.fullmatch(r"([A-G]#?\d)v(\d+)\.wav", name)
        if not m:
            continue
        key = int(ops.get("pitch_keycenter", note_to_midi(m.group(1))))
        zones.append(Zone(
            path=SALAMANDER / "48khz24bit" / name,
            pitch=key - float(ops.get("tune", 0)) / 100.0,
            lovel=int(ops.get("lovel", 1)), hivel=int(ops.get("hivel", 127)),
            layer=int(m.group(2)) - 1,
            lokey=int(ops["lokey"]), hikey=int(ops["hikey"]),
        ))
    return zones


def _yin_pitch(x: np.ndarray, fmin: float = 30.0, fmax: float = 2000.0) -> float:
    """Median YIN f0 (Hz) over a few frames of the sustained part."""
    mono = x.mean(axis=1)
    n = 4096
    start = min(len(mono) - n - 1, int(0.25 * SR))
    ests = []
    for off in range(max(0, start), max(1, len(mono) - n), n // 2)[:8]:
        frame = mono[off:off + n].astype(np.float64)
        if len(frame) < n:
            break
        tau_max = int(SR / fmin)
        f = np.fft.rfft(frame, 2 * n)
        acf = np.fft.irfft(f * np.conj(f))[:tau_max]
        energy = np.cumsum(frame ** 2)
        e0 = energy[-1]
        taus = np.arange(tau_max)
        e_tau = e0 - np.concatenate([[0.0], energy[:tau_max - 1]])
        d = e0 + e_tau - 2 * acf
        d[0] = 0
        cmnd = d * taus / np.maximum(np.cumsum(d), 1e-12)
        cmnd[0] = 1
        lo = int(SR / fmax)
        below = np.where(cmnd[lo:] < 0.15)[0]
        tau = lo + (below[0] if len(below) else int(np.argmin(cmnd[lo:])))
        while tau + 1 < tau_max and cmnd[tau + 1] < cmnd[tau]:
            tau += 1
        ests.append(SR / tau)
    return float(np.median(ests)) if ests else 0.0


def _folder_offset(files: list[tuple[Path, int]], key: str) -> int:
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    if key in cache:
        return cache[key]
    diffs = []
    for path, named in files[:: max(1, len(files) // 6)]:
        f0 = _yin_pitch(load(path))
        if f0 > 0:
            detected = 69 + 12 * np.log2(f0 / 440.0)
            diffs.append(round((detected - named) / 12))
    offset = int(np.median(diffs)) * 12 if diffs else 0
    cache[key] = offset
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1))
    return offset


def fine_tune_cents(path: Path, midi: float, sustained: bool = False) -> float:
    """Cents the sample sounds away from `midi`, read off the spectral peak
    nearest the expected fundamental and its 2nd and 3rd partials. Returns 0
    when no clear partial sits within a quarter tone (unpitched or noisy).
    A sustained sample is read on its held body (0.5-2.0 s), because a bowed or
    blown attack scoops up to the pitch; anything else on the attack (0.04-0.45 s)."""
    x = load(path).mean(axis=1)
    a, b = (0.5, 2.0) if sustained and len(x) > int(0.6 * SR) else (0.04, 0.45)
    a, b = int(a * SR), int(b * SR)
    frame = x[a:b] if len(x) > b else x[a:]
    n = 1 << 18
    spec = np.abs(np.fft.rfft(frame * np.hanning(len(frame)), n))
    freqs = np.fft.rfftfreq(n, 1 / SR)
    f0 = 440.0 * 2 ** ((midi - 69) / 12)
    found = []
    for h, w in ((1, 1.0), (2, 0.6), (3, 0.3)):
        band = (freqs >= f0 * h * 2 ** (-0.5 / 12)) & (freqs <= f0 * h * 2 ** (0.5 / 12))
        wide = (freqs >= f0 * h * 2 ** (-2 / 12)) & (freqs <= f0 * h * 2 ** (2 / 12))
        if not band.any():
            continue
        peak = spec[band].max()
        if peak < spec[wide].max() * 0.999 or peak < np.median(spec[wide]) * 8:
            continue
        fpk = freqs[band][np.argmax(spec[band])]
        found.append((w, 1200 * np.log2(fpk / (f0 * h))))
    if not found:
        return 0.0
    return float(sum(w * c for w, c in found) / sum(w for w, _ in found))


def _tuned(parsed: list[tuple[Path, int, int, int]], offset: int, sustained: bool) -> dict[str, float]:
    """Per-file fine tuning (cents) for a folder, cached in build/ (sustained keys end in "@sus")."""
    cache = json.loads(TUNE_CACHE.read_text()) if TUNE_CACHE.exists() else {}
    tag = "@sus" if sustained else ""
    dirty = False
    for p, note, _, _ in parsed:
        key = str(p.relative_to(SAMPLES)) + tag
        if key not in cache:
            cache[key] = round(fine_tune_cents(p, note + offset, sustained), 1)
            dirty = True
    if dirty:
        TUNE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        TUNE_CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True))
    return {str(p.relative_to(SAMPLES)): cache[str(p.relative_to(SAMPLES)) + tag] for p, *_ in parsed}


def vsco(folder: str, pattern: str, layers: list[str], sustained: bool = False) -> list[Zone]:
    """Index a VSCO folder. `pattern` is a regex with groups note, layer, rr?
    `sustained` tunes each sample on its held body instead of its attack."""
    base = VSCO / folder
    rx = re.compile(pattern)
    parsed = []
    for p in sorted(base.glob("*.wav")):
        m = rx.fullmatch(p.name)
        if not m:
            continue
        gd = m.groupdict()
        layer = gd.get("layer") or layers[0]
        if layer not in layers:
            continue
        parsed.append((p, note_to_midi(gd["note"]), layers.index(layer),
                       int(gd.get("rr") or 1) - 1))
    if not parsed:
        hint = "" if base.exists() else " (sample libraries not installed: run ./setup.sh without --no-samples)"
        raise FileNotFoundError(f"no samples matched in {base}{hint}")
    offset = _folder_offset([(p, n) for p, n, _, _ in parsed], folder)
    cents = _tuned(parsed, offset, sustained)
    n_layers = len(layers)
    zones = []
    for p, note, layer, rr in parsed:
        lo = 1 + layer * 127 // n_layers
        hi = (layer + 1) * 127 // n_layers
        pitch = note + offset + cents[str(p.relative_to(SAMPLES))] / 100.0
        zones.append(Zone(p, float(pitch), lo, hi, layer, rr))
    return zones
