"""Render the soundtrack.

    uv run render.py [--out out] [--seed 7] [--qc] [--excerpt 10 35]
    uv run render.py --selftest

Composes the cue with the project's music/arrangement.py, whose compose(seed) returns a
scorekit.score.Score (README.md, "Music"), and writes out/soundtrack.wav, out/stems/*.wav
(48 kHz, 24-bit, sample-aligned) and manifest.json (tempo, bar grid, section starts).
--excerpt also writes out/excerpt.wav, a slice of the same render for the audio judge.
--selftest renders eight bars of synthesized C major to out/selftest/ (no samples needed).
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf

from scorekit import synth
from scorekit.instruments import STEMS, registry
from scorekit.library import SR
from scorekit.mix import master, process_stems
from scorekit.percussion import PERC, render_percussion
from scorekit.score import Score
from scorekit.timing import Grid

HERE = Path(__file__).resolve().parent
SYNTH_STEM = {"pluck": "synth", "sub": "bass"}


def compose(seed: int) -> Score:
    """The project's score, from music/arrangement.py."""
    if not (HERE / "arrangement.py").exists():
        sys.exit(f"no score: create {HERE / 'arrangement.py'} defining compose(seed) -> Score "
                 "(README.md, \"Music\")")
    sys.path.insert(0, str(HERE))
    module = importlib.import_module("arrangement")
    if not hasattr(module, "compose"):
        sys.exit(f"{HERE / 'arrangement.py'} defines no compose(seed) (README.md, \"Music\")")
    return module.compose(seed)


def selftest_score(seed: int) -> Score:
    """Eight bars of C - Am - F - G on the synth pluck, sub bass, kick and claps."""
    sc = Score(Grid(bpm=120.0, bar0_at=0.5, total=17.0, sections=[("test", 0, 0.0)], speech=[]),
               harmony=[(b, 1, sym) for b, sym in enumerate(["C", "Am", "F", "G"] * 2)], seed=seed)
    for bar, length, ch in sc.spans(0, 8):
        for k in range(int(length * 8)):
            sc.add("pluck", bar * 4 + k * 0.5, 0.45, 60 + ch.intervals[k % len(ch.intervals)] + ch.root, 80)
        sc.add("sub", bar * 4, 3.9, 36 + ch.root, 90)
        for b in (0, 2):
            sc.hit("kick", bar * 4 + b, 100)
        for b in (1, 3):
            sc.hit("clap", bar * 4 + b, 80)
    return sc


def _render_inst(args):
    name, notes, length, seed = args
    from scorekit.sampler import render_part
    return name, render_part(notes, registry()[name], length, seed)


def render_synth(notes, length: int, seed: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    out = {s: np.zeros((length, 2)) for s in set(SYNTH_STEM.values())}
    for n in sorted(notes, key=lambda n: n.t):
        x = synth.pluck(n.pitch, n.dur, n.vel, rng) if n.inst == "pluck" else synth.sub(n.pitch, n.dur, n.vel)
        start = int(round(n.t * SR))
        end = min(length, start + len(x))
        if end > start:
            out[SYNTH_STEM[n.inst]][start:end] += x[: end - start]
    return out


def render_dry(score: Score, length: int, seed: int) -> dict[str, np.ndarray]:
    """Every instrument rendered dry into its stem; sampled ones in parallel processes."""
    dry = {s: np.zeros((length, 2)) for s in STEMS}
    jobs, perc, syn = [], [], []
    for k, (name, notes) in enumerate(sorted(score.notes.items())):
        if name in SYNTH_STEM:
            syn += notes
        elif name in PERC:
            perc += notes
        elif name in registry():
            jobs.append((name, notes, length, seed * 1000 + k))
        else:
            raise KeyError(f"no renderer for instrument {name!r}")
    if jobs:
        with ProcessPoolExecutor(max_workers=min(16, len(jobs))) as pool:
            for name, buf in pool.map(_render_inst, jobs):
                dry[registry()[name].stem] += buf
    dry["percussion"] += render_percussion(perc, length, seed)
    for stem, buf in render_synth(syn, length, seed).items():
        dry[stem] += buf
    return dry


def render(score: Score, out: Path, seed: int) -> tuple[dict, np.ndarray]:
    t_start = time.time()
    total = score.grid.total
    length = int((total + 4.0) * SR)
    wet = process_stems(render_dry(score, length, seed), score.automation, seed)
    mix, stems, report = master(wet, total)
    (out / "stems").mkdir(parents=True, exist_ok=True)
    sf.write(out / "soundtrack.wav", mix.astype(np.float32), SR, subtype="PCM_24")
    for name, x in stems.items():
        sf.write(out / "stems" / f"{name}.wav", x.astype(np.float32), SR, subtype="PCM_24")
    man = score.grid.manifest()
    man.update({
        "file": f"{out.name}/soundtrack.wav",
        "stems": {k: f"{out.name}/stems/{k}.wav" for k in STEMS},
        "format": "WAV PCM 24-bit, 48 kHz, stereo",
        "loudness": report,
        "note_count": sum(len(v) for v in score.notes.values()),
        "render_seconds": round(time.time() - t_start, 1),
    })
    return man, mix


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", type=Path, default=HERE / "out")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--qc", action="store_true", help="also write QC plots to out/qc/")
    ap.add_argument("--qc-only", action="store_true", help="skip rendering; QC the existing files")
    ap.add_argument("--excerpt", type=float, nargs=2, metavar=("FROM", "TO"),
                    help="also write out/excerpt.wav for the given seconds")
    ap.add_argument("--selftest", action="store_true", help="render a short synth-only test to out/selftest/")
    a = ap.parse_args()
    if a.qc_only:
        from scorekit.qc import run_qc
        print(json.dumps(run_qc(a.out, json.loads((HERE / "manifest.json").read_text())), indent=1))
        return
    if a.selftest:
        out = HERE / "out" / "selftest"
        man, _ = render(selftest_score(a.seed), out, a.seed)
        (out / "manifest.json").write_text(json.dumps(man, indent=1))
        print(json.dumps({k: man[k] for k in ("loudness", "note_count", "render_seconds")}, indent=1))
        return
    man, mix = render(compose(a.seed), a.out, a.seed)
    (HERE / "manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps({k: man[k] for k in ("loudness", "note_count", "render_seconds")}, indent=1))
    if a.excerpt:
        lo, hi = (int(v * SR) for v in a.excerpt)
        sf.write(a.out / "excerpt.wav", mix[lo:hi].astype(np.float32), SR, subtype="PCM_24")
    if a.qc:
        from scorekit.qc import run_qc
        print(json.dumps(run_qc(a.out, man), indent=1))


if __name__ == "__main__":
    main()
