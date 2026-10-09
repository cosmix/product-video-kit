#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fonttools==4.65.0",
# ]
# ///
"""Find the font files design.json names by family and write brand/fonts/resolved.json.

Usage (from the project root):
    uv run tools/fonts.py [--check]

A font role in design.json is a file path (ends in .ttf, .otf or .ttc) or a family name.
`fonts.family` fills regular (400), bold (700), italic and bold_italic (700 italic) for each of
those the file does not set itself. For every role that names a family, the script looks in
brand/fonts/, then in the fonts installed on this machine; it never touches the network. A variable font becomes a static instance at the wanted weight. Installed fonts
are used where they are and never copied into the project; files derived from them go to
brand/fonts/.local/, those derived from files in brand/fonts/ go next to them. --check resolves
without writing, and exits 1 if a family is missing. MISSING and WARN lines start with the level, then the role or family and a colon.
"""

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont
from fontTools.varLib import instancer

logging.getLogger("fontTools").setLevel(logging.ERROR)  # timestamp notices from font files

ROOT = Path(__file__).resolve().parents[1]
DESIGN_JSON = ROOT / "design.json"
FONTS_DIR = ROOT / "brand" / "fonts"
LOCAL_DIR = FONTS_DIR / ".local"  # files derived from installed fonts: machine-specific, not shared
RESOLVED = FONTS_DIR / "resolved.json"
FONT_EXT = (".ttf", ".otf", ".ttc")
STYLES = {"regular": (400, False), "bold": (700, False), "italic": (400, True),
          "bold_italic": (700, True), "mono": (400, False)}
FILLED_BY_FAMILY = ("regular", "bold", "italic", "bold_italic")
SOURCES = ("brand/fonts", "installed")
MAC_DIRS = ("/System/Library/Fonts", "/System/Library/Fonts/Supplemental", "/Library/Fonts", "~/Library/Fonts")
LINUX_DIRS = ("/usr/share/fonts", "/usr/local/share/fonts", "~/.fonts", "~/.local/share/fonts")


@dataclass
class Face:
    path: Path
    index: int  # face number inside a TTC, else 0
    family: str
    weight: int
    italic: bool
    axes: dict  # variable axes: tag -> (min, default, max)


@dataclass
class Pick:
    face: Face
    weight: int  # the weight the file will have
    italic: bool
    exact: bool


def is_family(value) -> bool:
    return not str(value).lower().endswith(FONT_EXT)


def font_roles(fonts: dict) -> dict:
    """{role key: path or family name}; `family` fills the four roles the file leaves unset."""
    roles = {f"fonts.{k}": v for k, v in fonts.items() if k not in ("weights", "family")}
    if fonts.get("family"):
        roles = {**{f"fonts.{k}": fonts["family"] for k in FILLED_BY_FAMILY}, **roles}
    roles.update({f"fonts.weights.{w}": v for w, v in fonts.get("weights", {}).items()})
    return roles


def wanted(fonts: dict) -> dict:
    """{role key: (family, weight, italic)} for every role design.json names by family."""
    out = {}
    for key, value in font_roles(fonts).items():
        if not isinstance(value, str) or not value.strip():
            raise SystemExit(f"{key} = {value!r}: expected a font file path or a family name")
        if not is_family(value):
            continue
        name = key.rsplit(".", 1)[-1]
        if key.startswith("fonts.weights."):
            if not name.isdigit():
                raise SystemExit(f"{key}: the weight must be an integer")
            style = (int(name), False)
        elif name in STYLES:
            style = STYLES[name]
        else:
            raise SystemExit(f"unknown key {key}")
        out[key] = (value.strip(), *style)
    return out


def face_of(path: Path, index: int, font: TTFont) -> Face | None:
    try:
        names, head, os2 = font["name"], font["head"], font.get("OS/2")
        family = names.getDebugName(16) or names.getDebugName(1)
        if not family:
            return None
        weight = os2.usWeightClass if os2 else (700 if head.macStyle & 1 else 400)
        italic = bool((os2.fsSelection & 1) if os2 else 0) or bool(head.macStyle & 2)
        axes = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes} if "fvar" in font else {}
        return Face(path, index, family, int(weight), italic, axes)
    except Exception:  # fontTools raises many types for a damaged table
        return None


def read_faces(path: Path) -> list:
    """Every face of a font file (all faces of a TTC); [] when it does not parse."""
    try:
        if path.suffix.lower() == ".ttc":
            with TTCollection(path, lazy=True) as coll:
                faces = [face_of(path, i, f) for i, f in enumerate(coll.fonts)]
        else:
            with TTFont(path, lazy=True) as font:
                faces = [face_of(path, 0, font)]
    except Exception:  # not a font, or damaged
        return []
    return [f for f in faces if f]


def pick(faces: list, weight: int, italic: bool) -> Pick:
    """The face closest to the wanted weight and style; a variable font reaches any weight in its range."""
    def option(f: Face):
        got = min(max(weight, round(f.axes["wght"][0])), round(f.axes["wght"][2])) if "wght" in f.axes else f.weight
        styled = f.italic == italic or "ital" in f.axes or "slnt" in f.axes
        got_italic = italic if styled else f.italic
        return (got_italic != italic, abs(got - weight), "wght" in f.axes), f, got, got_italic
    key, face, got, got_italic = min((option(f) for f in faces), key=lambda o: o[0])
    return Pick(face, got, got_italic, key[:2] == (False, 0))


def dirname(family: str) -> str:
    return re.sub(r"[^\w .-]", "", family).strip() or "family"


def derived(source: Path, out: Path, build) -> Path:
    """`out`, built by build(out) unless it is already newer than its source file."""
    if not (out.is_file() and out.stat().st_mtime >= source.stat().st_mtime):
        out.parent.mkdir(parents=True, exist_ok=True)
        build(out)
    return out


def make_instance(p: Pick, out: Path) -> None:
    f = p.face
    limits = {tag: dflt for tag, (_, dflt, _) in f.axes.items()}
    limits["wght"] = p.weight
    if p.italic and not f.italic:  # italic through the ital or slnt axis
        for tag, at in (("ital", 2), ("slnt", 0)):
            if tag in f.axes:
                limits[tag] = f.axes[tag][at]
                break
    static = instancer.instantiateVariableFont(TTFont(f.path, fontNumber=f.index), limits)
    if "OS/2" in static:
        static["OS/2"].usWeightClass = p.weight
        static["OS/2"].fsSelection |= 1 if p.italic else 0
    static["head"].macStyle |= 2 if p.italic else 0
    static.save(out)


def materialize(p: Pick, family: str, source: str) -> Path:
    """A single-face static file for the pick; installed fonts only ever produce files in .local."""
    f = p.face
    directory = LOCAL_DIR if source == "installed" else FONTS_DIR / dirname(family)
    ext = ".otf" if f.path.suffix.lower() == ".otf" else ".ttf"
    if "wght" in f.axes:
        stem = re.sub(r"\W+", "", f.family)
        name = f"{stem}-{p.weight}{'-Italic' if p.italic else ''}{ext}"
        return derived(f.path, directory / name, lambda out: make_instance(p, out))
    if f.path.suffix.lower() == ".ttc" and f.index:
        def extract(out):
            TTFont(f.path, fontNumber=f.index).save(out)
        return derived(f.path, directory / f"{f.path.stem}-{f.index}{ext}", extract)
    return f.path


def write_atomic(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    part.write_bytes(data)
    os.replace(part, target)


def installed_files() -> list:
    """Font files installed on this machine: fc-list on Linux, plus the usual font folders."""
    files = set()
    if sys.platform != "darwin" and shutil.which("fc-list"):
        try:
            out = subprocess.run(["fc-list", "--format", "%{file}\\n"], capture_output=True, text=True, timeout=60).stdout
            files.update(Path(line) for line in out.splitlines() if line)
        except (OSError, subprocess.SubprocessError):
            pass  # the folder scan below still runs
    for d in MAC_DIRS if sys.platform == "darwin" else LINUX_DIRS:
        d = Path(d).expanduser()
        if d.is_dir():
            files.update(p for p in d.rglob("*") if p.is_file())
    return sorted({p.resolve() for p in files if p.suffix.lower() in FONT_EXT and p.is_file()})


def index_of(files) -> dict:
    index = {}
    for path in files:
        for face in read_faces(path):
            index.setdefault(face.family.casefold(), []).append(face)
    return index


class Finder:
    """Faces of a family per source; each source is read at most once."""

    def __init__(self):
        self.indexes = {}

    def faces(self, source: str, family: str) -> list:
        key = family.casefold()
        if source not in self.indexes:
            files = [p for p in sorted(FONTS_DIR.rglob("*")) if p.suffix.lower() in FONT_EXT and LOCAL_DIR not in p.parents] \
                if source == "brand/fonts" else installed_files()
            self.indexes[source] = index_of(files)
        return self.indexes[source].get(key, [])


def resolve_role(finder: Finder, family: str, weight: int, italic: bool):
    """(source, pick): the first source with an exact match, else the nearest inexact one; None if no source has the family."""
    best = None
    for source in SOURCES:
        faces = finder.faces(source, family)
        if faces:
            p = pick(faces, weight, italic)
            if p.exact:
                return source, p
            best = best or (source, p)
    return best


def shown(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def label(weight: int, italic: bool) -> str:
    return f"{weight}{' italic' if italic else ''}"


def resolve_all(roles: dict, check: bool):
    """({role key: path}, {family: [role keys]} not found); prints one line per role and the warnings."""
    finder, paths, missing = Finder(), {}, {}
    for key, (family, weight, italic) in roles.items():
        found = resolve_role(finder, family, weight, italic)
        if not found:
            missing.setdefault(family, []).append(key)
            continue
        source, p = found
        try:
            paths[key] = materialize(p, family, source) if not check else p.face.path
        except Exception as e:  # fontTools raises many types while instancing
            raise SystemExit(f"MISSING {family}: cannot make a {label(p.weight, p.italic)} file from {p.face.path}: {e}")
        print(f"{key:<22} {family:<20} {source:<12} {shown(paths[key])}")
        if not p.exact:
            print(f"WARN {key}: {family} wanted {label(weight, italic)}, got {label(p.weight, p.italic)}")
    for family, keys in missing.items():
        print(f"MISSING {family}: not found in brand/fonts/ or the installed fonts (roles: {', '.join(keys)}); install it on this"
              f" machine, or put its font files (TTF/OTF/TTC or a variable font) and its licence file in brand/fonts/{dirname(family)}/,"
              " then rerun `uv run tools/fonts.py`")
    return paths, missing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="resolve without writing")
    check = ap.parse_args().check
    if not DESIGN_JSON.is_file():
        print("nothing to resolve: design.json is absent")
        return 0
    raw = DESIGN_JSON.read_bytes()
    try:
        design = json.loads(raw)
        fonts = design.get("fonts", {})
        roles = wanted(fonts)
    except (ValueError, AttributeError, TypeError) as e:  # not JSON, or fonts / weights of the wrong shape
        raise SystemExit(f"{DESIGN_JSON}: cannot read the fonts: {e}")
    if not roles:
        print("nothing to resolve: design.json names no font family")
        return 0
    paths, missing = resolve_all(roles, check)
    if missing:
        return 1
    if not check:
        out = {key: shown(path) for key, path in paths.items()}
        out["design_json_sha256"] = hashlib.sha256(raw).hexdigest()
        write_atomic(RESOLVED, (json.dumps(out, indent=2) + "\n").encode())
    return 0


if __name__ == "__main__":
    sys.exit(main())
