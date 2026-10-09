"""Smoothness check for captured clips.

For each clip: frame-time jitter from the container timestamps, the share of
frames that repeat their predecessor (no pixel changed by more than codec
noise), and that share restricted to frames where the scripted cursor moved.
Repeats are expected only where nothing on the page animates.

    uv run python -m webcap.verify [--dir captures/web]
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

from webcap.capture import OUT

W, H = 1920, 1080


def frame_times(path: Path) -> np.ndarray:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=pts_time",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return np.array([float(x.strip(",")) for x in out.split()])


def frame_diffs(path: Path) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={W}:{H}:flags=area,format=gray",
         "-f", "rawvideo", "-"],
        capture_output=True, check=True,
    ).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.int16)
    # Largest per-pixel change: a frame with none at all repeats its predecessor.
    return np.array([np.abs(b - a).max() for a, b in zip(frames, frames[1:])])


def check(path: Path, entry: dict) -> dict:
    times = frame_times(path)
    deltas = np.diff(times)
    diffs = frame_diffs(path)
    dup = diffs <= 2
    cursor = entry.get("cursor", [])
    moving = np.array([
        (a["x"], a["y"]) != (b["x"], b["y"]) for a, b in zip(cursor, cursor[1:])
    ][: len(dup)], dtype=bool)
    return {
        "frames": int(len(times)),
        "fps_mean": round(float(1 / deltas.mean()), 3),
        "frame_time_jitter_ms": round(float(deltas.std() * 1000), 4),
        "duplicate_ratio": round(float(dup.mean()), 4),
        "moving_frames": int(moving.sum()),
        "duplicate_ratio_while_cursor_moves": round(float(dup[moving].mean()), 4) if moving.any() else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", type=Path, default=OUT)
    args = parser.parse_args()
    manifest_path = args.dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for name, entry in manifest["clips"].items():
        path = args.dir / name
        if not path.exists():
            continue
        entry["smoothness"] = check(path, entry)
        print(name, entry["smoothness"])
    partial = manifest_path.with_suffix(".tmp.json")
    partial.write_text(json.dumps(manifest, indent=1))
    partial.replace(manifest_path)


if __name__ == "__main__":
    main()
