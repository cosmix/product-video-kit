"""Asset lookup across the team's output folders, with synthetic placeholders.

A key is "<kind>:<name>": "web:<clip>", "tui:<clip>", "motion:<scene>" (opaque),
"motion_alpha:<scene>" (its transparent variant), "broll:<clip>", "still:<path>" (captures/<path>.png,
else <path> from the project root), "image:<card>" (a generated card in build/art/). Real files win; a missing asset is
replaced by a generated placeholder of the right shape so the edit can be built and timed
without it.
"""

import json
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import design
from .decode import Probe, probe
from .hw import fast_h264

ROOT = Path(__file__).resolve().parents[2]
BUILD = Path(__file__).resolve().parents[1] / "build"
SOUNDTRACK = ROOT / "music" / "out" / "soundtrack.wav"  # absent in a video without music
VIDEO_EXT = (".mov", ".mp4", ".mkv", ".webm")

DIRS = {
    "web": ROOT / "captures" / "web",
    "tui": ROOT / "captures" / "tui",
    "motion": ROOT / "motion" / "out",
    "broll": ROOT / "broll" / "candidates",
}
MANIFESTS = {
    "web": ROOT / "captures" / "web" / "manifest.json",
    "tui": ROOT / "captures" / "tui" / "manifest.json",
    "motion": ROOT / "motion" / "out" / "manifest.json",
    "broll": ROOT / "broll" / "manifest.json",
}

# placeholder shapes: (width, height, duration, alpha)
PLACEHOLDER = {
    "web": (3840, 2160, 40.0, False),
    "tui": (3200, 1800, 30.0, False),
    "motion": (1920, 1080, 16.0, False),
    "motion_alpha": (1920, 1080, 12.0, True),
    "broll": (1920, 1080, 12.0, False),
}


@dataclass
class Asset:
    key: str
    path: Path
    info: Probe | None
    marks: dict = field(default_factory=dict)      # event -> source time
    entry: dict = field(default_factory=dict)      # raw manifest entry
    placeholder: bool = False
    still: bool = False

    def mark(self, event: str, default: float | None) -> float | None:
        if event in self.marks:  # an exact name wins over an earlier mark that merely contains it
            return self.marks[event]
        for k, v in self.marks.items():
            if event.lower() in k.lower():
                return v
        return default

    @property
    def cursor(self) -> list | None:
        c = self.entry.get("cursor") or self.entry.get("cursor_track")
        if not c:
            return None
        return [(p["t"], p["x"], p["y"], 1.0 if p.get("down") else 0.0) for p in c]


def _entries(obj):
    """Every dict in a manifest that names a file."""
    if isinstance(obj, dict):
        if any(k in obj for k in ("file", "path", "output")):
            yield obj
        for v in obj.values():
            yield from _entries(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _entries(v)


def _entry_file(e: dict) -> str:
    return str(e.get("file") or e.get("path") or e.get("output"))


@lru_cache(maxsize=None)
def manifest(kind: str) -> dict:
    """file name -> manifest entry (names, not stems: end.mp4 and a stale end.mov differ)"""
    p = MANIFESTS.get(kind)
    if not p or not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}
    return {Path(_entry_file(e)).name: e for e in _entries(data)}


def _marks(entry: dict) -> dict:
    raw = entry.get("marks") or entry.get("events") or []
    if isinstance(raw, dict):
        return {k: float(v) for k, v in raw.items()}
    out = {}
    for m in raw:
        name = m.get("event") or m.get("name") or m.get("label")
        if name is not None and name not in out:
            out[name] = float(m["t"])
    return out


def _find(kind: str, name: str, alpha: bool) -> Path | None:
    d = DIRS.get(kind.replace("_alpha", ""))
    if not d or not d.exists():
        return None
    cands = sorted(p for p in d.iterdir() if p.suffix.lower() in VIDEO_EXT and p.stem.startswith(name)
                   and not p.stem.endswith((".tmp", ".part")))  # teammates write to temp names, then rename
    if not cands:
        return None
    if alpha:
        pref = [p for p in cands if p.suffix.lower() == ".mov" or "alpha" in p.stem]
        cands = pref or cands
    else:
        pref = [p for p in cands if "alpha" not in p.stem]
        cands = pref or cands
    exact = [p for p in cands if p.stem == name]
    return (exact or cands)[0]


def _style() -> tuple:
    """Placeholder label font (escaped for drawtext) and colours: text, secondary, background."""
    font = design.font(500).replace(":", "\\:")  # quoted in drawtext; a colon still needs its escape
    return (font, *(design.color(k).replace("#", "0x") for k in ("text", "secondary", "background")))


def _still_placeholder(name: str) -> Path:
    """A labelled PNG for a missing still, so drafts render before the capture exists."""
    out = BUILD / "placeholders" / f"still_{name.replace('/', '_')}.png"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    w, h = 1920, 1080
    font, fg, fg2, bg = _style()
    src = (f"color=c={bg}:s={w}x{h},drawgrid=w={w // 16}:h={h // 9}:t=2:c={fg2}@0.3,"
           f"drawtext=fontfile='{font}':text='still\\: {name}':fontcolor={fg}:fontsize={h // 14}:"
           f"x=(w-tw)/2:y=(h-th)/2")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", src, "-frames:v", "1", str(out)],
                   check=True)
    return out


def _placeholder(kind: str, name: str) -> Path:
    w, h, dur, alpha = PLACEHOLDER[kind]
    out = BUILD / "placeholders" / f"{kind}_{name}.{'mov' if alpha else 'mp4'}"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    fs = h // 14
    font, fg, fg2, bg = _style()
    text = (f"drawtext=fontfile='{font}':text='{kind}\\: {name}':fontcolor={fg}:fontsize={fs}:"
            f"x=(w-tw)/2:y=h*0.18,"
            f"drawtext=fontfile='{font}':text='%{{pts\\:hms}}':fontcolor={fg2}:fontsize={fs}:"
            f"x=(w-tw)/2:y=h*0.72")
    if alpha:
        src = (f"color=c=black@0.0:s={w}x{h}:r=60:d={dur},format=yuva444p10le,"
               f"drawbox=x=iw*0.3:y=ih*0.35:w=iw*0.4:h=ih*0.3:color={fg2}@0.5:t=6,{text}")
        enc = ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"]
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", src, *enc, str(out)]
    else:
        bars = (f"testsrc2=s={w // 3}x{h // 3}:r=60:d={dur}[b];"
                f"color=c={bg}:s={w}x{h}:r=60:d={dur}[bg];"
                f"[bg][b]overlay=(W-w)/2:(H-h)/2,drawgrid=w={w // 16}:h={h // 9}:t=2:c={fg2}@0.3,{text},format=yuv420p")
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", bars, *fast_h264("p4", 24),
               "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", str(out)]
    subprocess.run(cmd, check=True)
    return out


def _readable(path: Path) -> bool:
    """False for a file a teammate is still writing (no moov atom / truncated header)."""
    try:
        probe(str(path))
        return True
    except subprocess.CalledProcessError:
        print(f"  asset not readable yet, using a placeholder: {path.name}")
        return False


_SEEN: dict[str, Asset] = {}


def resolve(key: str) -> Asset:
    if key not in _SEEN:
        _SEEN[key] = _resolve(key)
    return _SEEN[key]


def _resolve(key: str) -> Asset:
    kind, name = key.split(":", 1)
    if kind == "still":
        path = ROOT / "captures" / f"{name}.png"
        if not path.exists():
            path = ROOT / name
        if path.exists():
            return Asset(key, path, None, still=True)
        return Asset(key, _still_placeholder(name), None, still=True, placeholder=True)
    if kind == "image":  # typographic cards generated by editkit.cards
        path = BUILD / "art" / f"{name}.png"
        return Asset(key, path, None, still=True, placeholder=not path.exists())
    alpha = kind.endswith("_alpha")
    base = kind.replace("_alpha", "")
    path = _find(kind, name, alpha)
    entry = {}
    if path is not None and _readable(path):
        entry = manifest(base).get(path.name, {})
        return Asset(key, path, probe(str(path)), _marks(entry), entry)
    path = _placeholder(kind, name)
    return Asset(key, path, probe(str(path)), {}, {}, placeholder=True)


def status() -> list[tuple[str, str]]:
    """(key, 'real' | 'placeholder') for every asset resolved so far."""
    return [(k, "placeholder" if a.placeholder else "real") for k, a in sorted(_SEEN.items())]
