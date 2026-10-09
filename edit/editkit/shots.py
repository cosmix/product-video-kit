"""Helpers the EDL is written with: narration word times, manifest sync, shot builders."""

import json
import sys
from functools import lru_cache
from pathlib import Path

from .assets import ROOT, resolve
from .ease import Track
from .scene import Cursor, Plane, home_distance

WORDS = Path(__file__).resolve().parents[1] / "build" / "words.json"
D = home_distance(30.0)


@lru_cache(maxsize=1)
def timeline() -> dict:
    path = ROOT / "narration" / "timeline.json"
    if not path.exists():
        sys.exit(f"no {path}: build it with narration/build_timeline.py (README.md, \"Narration\")")
    return json.loads(path.read_text())


@lru_cache(maxsize=1)
def _words() -> dict:
    return json.loads(WORDS.read_text()) if WORDS.exists() else {}


def scene_starts() -> dict:
    """scene key -> start, plus "end" -> total."""
    out = {s["key"]: s["start"] for s in timeline()["scenes"]}
    out["end"] = timeline()["total"]
    return out


def narration(name: str) -> dict:
    hit = next((s for s in timeline()["narration"] if s["name"].endswith(name) or s["name"] == name), None)
    if hit is None:
        raise KeyError(f"no narration section {name!r} in narration/timeline.json (a silent section has none)")
    return hit


def word(section: str, text: str, nth: int = 0, fallback: float | None = None) -> float:
    """Master time at which `text` is spoken in a narration section (whisper timings)."""
    key = next((k for k in _words() if k.endswith(section)), None)
    hits = [w["start"] for w in _words().get(key, []) if w["w"].strip(",.").lower() == text.lower()]
    if len(hits) > nth:
        return hits[nth]
    if fallback is not None:
        return fallback
    raise KeyError(f"word {text!r} (#{nth}) not spoken in narration {section!r}; re-run words.py or re-anchor")


def word_end(section: str, text: str, nth: int = 0) -> float:
    key = next((k for k in _words() if k.endswith(section)), None)
    hits = [w["end"] for w in _words().get(key, []) if w["w"].strip(",.").lower() == text.lower()]
    return hits[nth] if len(hits) > nth else narration(section)["end"]


def sync(key: str, event: str, at: float, start: float, default: float) -> float:
    """src_in for a layer starting at `start` so that manifest `event` lands at master `at`.
    A negative src_in holds the clip's first frame until playback reaches it."""
    return resolve(key).mark(event, default) - (at - start)


def anchor(key: str, event: str, at: float, default: float) -> float:
    """Master time at which a clip (played from its start) must begin so `event` lands at `at`."""
    return at - resolve(key).mark(event, default)


def duration(key: str) -> float:
    a = resolve(key)
    return a.info.duration if a.info else 0.0


def cursor_for(key: str, fallback: list | None = None) -> Cursor | None:
    """The manifest's cursor track; `fallback` only stands in on placeholder footage."""
    asset = resolve(key)
    track = asset.cursor or (fallback if asset.placeholder else None)
    return Cursor(track) if track else None


def fullframe(key: str, start: float, end: float, **kw) -> Plane:
    kw.setdefault("pos", (960.0, 540.0, 0.0))
    return Plane(key, start, end, space="screen", shadow=False, radius=0.0, size=(1920.0, 1080.0), **kw)


def browser(key: str, start: float, end: float, **kw) -> Plane:
    return Plane(key, start, end, chrome="browser", **kw)


def terminal(key: str, start: float, end: float, title: str, **kw) -> Plane:
    return Plane(key, start, end, chrome="terminal", title=title, **kw)


def content_size(key: str) -> tuple[float, float]:
    """A capture's size in local px: 2x captures count at half size (CSS px)."""
    info = resolve(key).info
    w, h = info.width, info.height
    return (w / 2, h / 2) if w >= 3000 else (float(w), float(h))


def framed(plane: Plane, keys: list) -> Plane:
    """Drive a window's transform from framings of its content.

    keys: [(t, (u, v, span, pitch, yaw)[, ease])]. (u, v) is the content point (0..1) put at
    the frame centre, `span` the fraction of the content width that fills the frame width,
    pitch/yaw a gentle tilt in degrees (kept small so text stays readable)."""
    wc, hc = plane.size or content_size(plane.source)
    tb = Plane.titlebar_h if plane.chrome else 0.0
    h = hc + tb
    pos, scale, rot = [], [], []
    for k in keys:
        t, (u, v, span, pitch, yaw) = k[0], k[1]
        ease = k[2] if len(k) > 2 else "cubic"
        z = 1920.0 / (span * wc)
        cx, cy = u * wc, tb + v * hc
        pos.append((t, (960.0 - z * (cx - wc / 2), 540.0 - z * (cy - h / 2), 0.0), ease))
        scale.append((t, z, ease))
        rot.append((t, (pitch, yaw, 0.0), ease))
    plane.pos, plane.scale, plane.rot = Track(*pos), Track(*scale), Track(*rot)
    return plane
