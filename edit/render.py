"""Render the edit.

  uv run render.py                          full quality -> out/intro.mp4 (muxes out/mix.wav)
  uv run render.py --preview                540p30, no grain/DOF/motion blur -> out/preview.mp4
  uv run render.py --range 20 34            any mode, a time range only
  uv run render.py --contact [--every 2]    contact sheet (one frame every N s) -> out/contact*.png
  uv run render.py --frames 12.5 40         single frames -> build/frames/*.png
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from editkit import assets
from editkit.art import font
from editkit.compositor import PREVIEW, Compositor, Quality
from editkit.hw import fast_h264
from editkit.project import edl

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"


def encoder(path: Path, q: Quality, start: float, dur: float, audio: Path | None, fast: bool):
    w, h = q.res
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
           "-r", str(q.fps), "-i", "-"]
    if audio is not None:
        cmd += ["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(audio)]
    cmd += ["-vf", "scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p,"
                   "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"]
    if fast:
        cmd += [*fast_h264("p5", 20), "-profile:v", "high"]
    else:
        cmd += ["-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-crf", "14",
                "-x264-params", "aq-mode=3"]
    cmd += ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]
    if audio is not None:
        cmd += ["-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-shortest"]
    cmd += ["-movflags", "+faststart", str(path)]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def render_video(q: Quality, start: float, end: float, out: Path, audio: Path | None, fast: bool) -> None:
    tl = edl().build()
    comp = Compositor(tl, q)
    n = int(round((end - start) * q.fps))
    enc = encoder(out, q, start, end - start, audio, fast)
    t0 = time.time()
    for i in range(n):
        t = start + i / q.fps
        enc.stdin.write(comp.render(t))
        if i % q.fps == 0:
            comp.retire(t)
        if i and i % (q.fps * 5) == 0:
            el = time.time() - t0
            print(f"  t={t:6.2f}s  {i}/{n}  {i / el:5.1f} fps", file=sys.stderr, flush=True)
    enc.stdin.close()
    enc.wait()
    comp.close()
    print(f"wrote {out} ({n} frames in {time.time() - t0:.0f}s)")


def render_frames(q: Quality, times: list[float]) -> list[Image.Image]:
    tl = edl().build()
    comp = Compositor(tl, q)
    w, h = q.res
    imgs = []
    for t in times:
        buf = comp.render(t)
        imgs.append(Image.frombytes("RGB", (w, h), buf))
        comp.close()  # isolated frames: reopen decoders at the next seek point
    return imgs


def contact(q: Quality, start: float, end: float, every: float, cols: int = 4) -> list[Path]:
    times = list(np.arange(start, end, every))
    imgs = render_frames(q, times)
    tw = 480
    th = int(tw * 9 / 16)
    rows_per_sheet = 6
    per = cols * rows_per_sheet
    paths = []
    f = font(16, 500)
    for s in range(0, len(imgs), per):
        chunk = imgs[s:s + per]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * tw + (cols + 1) * 6, rows * (th + 26) + 6), (40, 40, 40))
        d = ImageDraw.Draw(sheet)
        for i, im in enumerate(chunk):
            x, y = 6 + (i % cols) * (tw + 6), 6 + (i // cols) * (th + 26)
            sheet.paste(im.resize((tw, th), Image.LANCZOS), (x, y))
            d.text((x + 4, y + th + 3), f"{times[s + i]:6.2f}s", font=f, fill=(230, 230, 230))
        p = OUT / f"contact_{start:05.1f}_{s // per:02d}.png"
        sheet.save(p)
        paths.append(p)
    return paths


def require_real_assets() -> None:
    """Refuse to render a video while any shot resolves to a placeholder."""
    for seg in edl().build().segments:
        for plane in seg.layers:
            if isinstance(plane.source, str):
                assets.resolve(plane.source)
    missing = [key for key, state in assets.status() if state != "real"]
    if missing:
        sys.exit("refusing to render, placeholders in use: " + ", ".join(missing)
                 + " (wait for the asset, or pass --allow-placeholders for a draft)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--range", nargs=2, type=float, metavar=("START", "END"))
    ap.add_argument("--out", type=Path)
    ap.add_argument("--contact", action="store_true")
    ap.add_argument("--every", type=float, default=2.0)
    ap.add_argument("--frames", nargs="+", type=float)
    ap.add_argument("--full-frames", action="store_true", help="--frames at full quality")
    ap.add_argument("--fast", "--nvenc", dest="fast", action="store_true",
                    help="fast encode instead of x264 at crf 14 (NVENC or VideoToolbox when they work, else x264 veryfast)")
    ap.add_argument("--allow-placeholders", action="store_true", help="render even if an asset is missing")
    a = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    if not (a.frames or a.contact or a.allow_placeholders):
        require_real_assets()
    q = PREVIEW if a.preview else Quality()
    total = edl().END
    start, end = a.range if a.range else (0.0, total)

    if a.frames:
        fq = Quality() if a.full_frames else Quality(res=(1920, 1080), fps=60, grain=0.0, dof=True,
                                                     motion_blur=False, decode_scale=0.5)
        d = HERE / "build" / "frames"
        d.mkdir(parents=True, exist_ok=True)
        for t, im in zip(a.frames, render_frames(fq, a.frames)):
            p = d / f"f_{t:07.3f}.png"
            im.save(p)
            print(p)
    elif a.contact:
        cq = Quality(res=(960, 540), fps=60, grain=0.0, dof=True, motion_blur=False, decode_scale=0.5)
        for p in contact(cq, start, end, a.every):
            print(p)
    else:
        mix = OUT / "mix.wav"
        audio = mix if mix.exists() else None
        name = "preview.mp4" if a.preview else "intro.mp4"
        if a.range:
            name = name.replace(".mp4", f"_{start:g}-{end:g}.mp4")
        render_video(q, start, end, a.out or OUT / name, audio, fast=a.fast or a.preview)
    for key, state in assets.status():
        if state != "real":
            print(f"  {state}: {key}")


if __name__ == "__main__":
    main()
