"""Audio mix: narration chain, music ducked under speech, quiet UI sound design, mastering.

  uv run mix.py        -> out/mix.wav (48 kHz stereo float), then loudness report

Narration: HPF 80 Hz, gentle presence, zero-phase de-esser, light compression, placed per
narration/timeline.json. Music: out/soundtrack.wav (or its stems, rhythm ducked less than
melody), ducked 8.5 dB under speech (rhythm stems 4.5) with a hold and smooth ramps, so gaps swell back up.
Sound design: synthesized whooshes on moving transitions and soft ticks on cursor clicks,
read from the EDL. Master: -14 LUFS integrated, true peak <= -1 dBTP.

Every part is optional. Without narration there is no voice bus and the music is not ducked;
without music the bed is silent. With neither, sound design keeps its own level (no loudness
target), and with no sound design either the mix is silence of the EDL's length, so the master
still gets an audio track.
"""

import subprocess
from pathlib import Path

import numpy as np
import pyloudnorm
import soundfile as sf
from scipy.ndimage import gaussian_filter1d, maximum_filter1d, minimum_filter1d, uniform_filter1d
from scipy.signal import butter, lfilter, resample_poly, sosfilt, sosfiltfilt

from editkit.assets import ROOT, SOUNDTRACK
from editkit.project import edl
from editkit.shots import timeline

SR = 48000
OUT = Path(__file__).resolve().parent / "out" / "mix.wav"
RHYTHM_STEMS = ("bass", "percussion", "drums", "kick", "groove")


def db(x):
    return 20 * np.log10(np.maximum(x, 1e-9))


def undb(x):
    return 10 ** (np.asarray(x) / 20)


def load(path: Path) -> np.ndarray:
    x, sr = sf.read(path, dtype="float64", always_2d=True)
    if sr != SR:
        x = resample_poly(x, SR, sr, axis=0)
    return x


def peaking(f0: float, gain_db: float, q: float) -> np.ndarray:
    """RBJ peaking biquad as a single SOS row."""
    a = 10 ** (gain_db / 40)
    w = 2 * np.pi * f0 / SR
    alpha = np.sin(w) / (2 * q)
    b = [1 + alpha * a, -2 * np.cos(w), 1 - alpha * a]
    den = [1 + alpha / a, -2 * np.cos(w), 1 - alpha / a]
    return np.array([[*(np.array(b) / den[0]), 1.0, den[1] / den[0], den[2] / den[0]]])


def envelope(x: np.ndarray, win_s: float) -> np.ndarray:
    n = max(int(win_s * SR), 1)
    return np.sqrt(np.maximum(uniform_filter1d(x * x, n), 0.0))


def smooth_gain(target_db: np.ndarray, attack_s: float, release_s: float) -> np.ndarray:
    """Gain reduction (<= 0 dB) with a fast attack and a one-pole release, loop free."""
    held = minimum_filter1d(target_db, size=max(int(attack_s * SR), 1) * 2 + 1)
    a = np.exp(-1 / (release_s * SR))
    return lfilter([1 - a], [1, -a], held - 0.0) if release_s > 0 else held


def voice_chain(x: np.ndarray) -> np.ndarray:
    x = sosfilt(butter(4, 80, "highpass", fs=SR, output="sos"), x)
    x = sosfilt(np.vstack([peaking(3200, 2.0, 0.8), peaking(220, -2.5, 1.4)]), x)
    # de-esser: attenuate a zero-phase 5-9 kHz band only while it is hot
    band = sosfiltfilt(butter(4, [5500, 9500], "bandpass", fs=SR, output="sos"), x)
    over = np.maximum(db(envelope(band, 0.004)) - (db(np.sqrt(np.mean(x * x))) - 2.0), 0.0)
    red = gaussian_filter1d(-np.minimum(over * 0.8, 6.0), SR * 0.002)
    x = x + band * (undb(red) - 1.0)
    # light compression: 2.5:1 above -22 dBFS RMS, soft knee
    lvl = db(envelope(x, 0.010))
    over = lvl + 22.0
    knee = 6.0
    gr = np.where(over <= -knee / 2, 0.0,
                  np.where(over >= knee / 2, over * (1 / 2.5 - 1),
                           (1 / 2.5 - 1) * (over + knee / 2) ** 2 / (2 * knee)))
    x = x * undb(smooth_gain(gr, 0.005, 0.12))
    return x


def narration_track(n: int) -> np.ndarray:
    out = np.zeros(n)
    if not timeline()["narration"]:
        print("no narration: no voice bus")
        return out
    for sec in timeline()["narration"]:
        x = load(ROOT / sec["file"]).mean(axis=1)
        y = voice_chain(x)
        i = int(round(sec["start"] * SR))
        out[i:i + len(y)] += y[: max(n - i, 0)]
    # voice to about -18 LUFS before the master stage
    loud = pyloudnorm.Meter(SR).integrated_loudness(out[:, None].repeat(2, 1))
    if not np.isfinite(loud):
        print("warning: narration is silent (below the -70 LUFS gate): voice loudness not normalised")
        return out
    return out * undb(-18.0 - loud)


def speech_activity(voice: np.ndarray) -> np.ndarray:
    """0..1 speech presence at audio rate, computed at a 1 kHz control rate: a 600 ms hold
    either side bridges commas and in-sentence pauses, ~250 ms ramps, so the bed only rises
    in real gaps instead of surging between phrases."""
    k = SR // 1000
    m = len(voice) // k
    # the filter can leave tiny negative energies in silence; clamp before the root
    env = np.sqrt(np.maximum(uniform_filter1d((voice[: m * k] ** 2).reshape(m, k).mean(axis=1), 30), 0.0))
    active = maximum_filter1d((db(env) > -42.0).astype(float), size=1200)
    curve = gaussian_filter1d(active, 250)
    return np.interp(np.arange(len(voice)) / k, np.arange(m), curve)


def busy_sections(n: int) -> np.ndarray:
    """Extra melodic ducking (dB) inside the EDL's BUSY scenes (dense score under dense
    narration), eased in and out over ~0.5 s."""
    busy = set(getattr(edl(), "BUSY", ()))
    scenes = timeline()["scenes"]
    mask = np.zeros(n // 480 + 1)
    for i, sc in enumerate(scenes):
        if sc["key"] in busy:
            end = scenes[i + 1]["start"] if i + 1 < len(scenes) else timeline()["total"]
            mask[int(sc["start"] * 100):int(end * 100)] = 1.0
    mask = gaussian_filter1d(mask, 25) * -3.5
    return np.interp(np.arange(n) / 480, np.arange(len(mask)), mask)


def music_track(n: int, voice: np.ndarray) -> np.ndarray:
    speech = speech_activity(voice)
    melodic, rhythm = undb(speech * (-8.5 + busy_sections(len(voice)))), undb(speech * -4.5)
    full = SOUNDTRACK
    if not full.exists():
        print(f"no music ({full.relative_to(ROOT)}): no music bed")
        return np.zeros((n, 2))
    song = _fit(load(full), n)
    meter = pyloudnorm.Meter(SR)
    stems = [_fit(load(p), n) for p in _current_stems(full)]
    rhythm_mask = [p.stem.lower().startswith(RHYTHM_STEMS) for p in _current_stems(full)]
    if len(stems) > 1 and abs(meter.integrated_loudness(sum(stems)) - meter.integrated_loudness(song)) < 1.5:
        mix = sum(x * (rhythm if r else melodic)[:, None] for x, r in zip(stems, rhythm_mask))
        print(f"music: {len(stems)} stems, {sum(rhythm_mask)} ducked as rhythm")
    else:
        print("music: full soundtrack")
        mix = song * melodic[:, None]  # stems missing or not a match for the soundtrack
    # carve the voice's presence band out of the bed while speech is up (dynamic EQ)
    carved = sosfilt(peaking(2200, -3.5, 0.9), mix, axis=0)
    mix = mix + (carved - mix) * speech[:, None]
    # music bed around -27.5 LUFS after ducking, i.e. well under the voice
    loud = meter.integrated_loudness(mix)
    return mix * undb(-27.5 - loud) if np.isfinite(loud) else mix


def _current_stems(full: Path) -> list[Path]:
    """Stems rendered with the current soundtrack (same length), ignoring stale leftovers."""
    d = SOUNDTRACK.parent / "stems"
    if not d.exists():
        return []
    want = sf.info(full).duration
    return sorted(p for p in d.glob("*.wav") if abs(sf.info(p).duration - want) < 0.05)


def _fit(x: np.ndarray, n: int) -> np.ndarray:
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    if len(x) >= n:
        return x[:n]
    return np.vstack([x, np.zeros((n - len(x), 2))])


# -- sound design ------------------------------------------------------------------------------

def whoosh(dur: float, rng: np.random.Generator) -> np.ndarray:
    n = int(dur * SR)
    t = np.linspace(0, 1, n)
    noise = rng.standard_normal((n, 2))
    # sweep a band-pass by filtering in blocks with a rising centre frequency
    out = np.zeros_like(noise)
    blocks = 24
    for k in range(blocks):
        a, b = k * n // blocks, (k + 1) * n // blocks
        fc = 300 + 2600 * np.sin(np.pi * (k + 0.5) / blocks) ** 2
        sos = butter(2, [fc * 0.6, fc * 1.6], "bandpass", fs=SR, output="sos")
        pad = min(a, 2048)
        out[a:b] = sosfilt(sos, noise[a - pad:b], axis=0)[pad:]
    env = np.sin(np.pi * t) ** 2.2
    y = sosfilt(butter(2, 7500, "lowpass", fs=SR, output="sos"), out, axis=0) * env[:, None]
    return y / (np.max(np.abs(y)) + 1e-9)


def tick(rng: np.random.Generator) -> np.ndarray:
    n = int(0.045 * SR)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * 1850 * t) * np.exp(-t / 0.006)
    click = sosfilt(butter(2, [2500, 7000], "bandpass", fs=SR, output="sos"), rng.standard_normal(n)) * np.exp(-t / 0.002)
    y = body * 0.6 + click * 0.5
    y /= np.max(np.abs(y))
    return np.stack([y, y * 0.92], axis=1)


def sound_design(n: int) -> np.ndarray:
    rng = np.random.default_rng(7)
    tl = edl().build()
    out = np.zeros((n, 2))

    def put(sig, t, gain_db):
        i = int(t * SR)
        if 0 <= i < n:
            m = min(len(sig), n - i)
            out[i:i + m] += sig[:m] * undb(gain_db)

    for seg in tl.segments:
        tr = seg.trans
        if tr.kind in ("push", "zoom"):
            put(whoosh(tr.dur + 0.35, rng), seg.start - 0.1, -34.5)
        for p in seg.layers:
            cur = getattr(p, "cursor", None)
            if cur is None:
                continue
            for c in cur.clicks:
                t = p.start + (c - p.src_in) / p.speed
                if p.start <= t < p.end:
                    put(tick(rng), t, -34.0)
    return out


# -- master ------------------------------------------------------------------------------------

def true_peak_limit(x: np.ndarray, ceiling_db: float = -1.6) -> np.ndarray:  # margin for AAC overshoot
    over = np.abs(resample_poly(x, 4, 1, axis=0)).max(axis=1).reshape(-1, 4).max(axis=1)
    need = np.minimum(1.0, undb(ceiling_db) / np.maximum(over, 1e-9))
    need = minimum_filter1d(need, size=int(0.003 * SR) * 2 + 1)  # 3 ms lookahead either side
    # hold each reduction for 40 ms, then ease it off, so the limiter never flutters
    r = gaussian_filter1d(maximum_filter1d(1 - need, size=int(0.04 * SR)), SR * 0.008)
    return x * np.minimum(1 - r, need)[:, None]


def measure(path: Path) -> str:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True)
    if r.returncode != 0:
        return f"loudness measurement failed (ffmpeg exit {r.returncode}): {r.stderr.strip()[-400:]}"
    tail = r.stderr[r.stderr.rfind("Summary"):]
    keep = [ln.strip() for ln in tail.splitlines() if ln.strip().startswith(("I:", "LRA:", "Peak:"))]
    return "  ".join(keep)


def main() -> None:
    total = edl().END
    n = int(round(total * SR))
    voice = narration_track(n)
    bed = voice[:, None].repeat(2, 1) + music_track(n, voice)
    mix = bed + sound_design(n)
    # the score carries its own fade to silence at the video's end; a short guard fade only
    fade_in, fade_out = min(int(0.25 * SR), n), min(int(0.3 * SR), n)
    mix[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    mix[n - fade_out:] *= (np.cos(np.linspace(0, np.pi, fade_out)) * 0.5 + 0.5)[:, None]
    meter = pyloudnorm.Meter(SR)
    with np.errstate(divide="ignore"):  # silence measures -inf LUFS
        audible = np.isfinite(meter.integrated_loudness(bed))
    if audible:
        for _ in range(3):
            mix *= undb(-14.0 - meter.integrated_loudness(mix))
            mix = true_peak_limit(mix)
    else:
        print("no narration or music: sound design at its own level, no loudness target")
        mix = true_peak_limit(mix)
    OUT.parent.mkdir(exist_ok=True)
    sf.write(OUT, mix.astype(np.float32), SR, subtype="FLOAT")
    print(f"wrote {OUT}")
    print(measure(OUT))


if __name__ == "__main__":
    main()
