"""The project's design file, design.json at the project root (README.md, "Design system"):
fonts, colours, grain and logo, every key optional. An unnamed font role falls back to a system
font; a named path must exist; a named family resolves through brand/fonts/resolved.json, which
tools/fonts.py writes. The brand skill generates the file from BRAND.md (README.md, "Brand")."""

import hashlib
import json
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESIGN_JSON = ROOT / "design.json"
HELP = f"{DESIGN_JSON} (README.md, \"Design system\")"
FONT_KEYS = {"regular", "bold", "italic", "bold_italic", "mono", "weights", "family"}
FONT_EXT = (".ttf", ".otf", ".ttc")  # a font role ending so is a path, anything else a family name
RESOLVED = ROOT / "brand" / "fonts" / "resolved.json"  # tools/fonts.py: role key -> font file
LOGO_KEYS = ("on_dark", "on_light")  # the logo for a dark ground, the logo for a light ground
COLORS = {"background": "#000000", "text": "#ffffff", "secondary": "#a0a0a0", "accent": "#ffffff"}
GRAIN = 0.022
SYSTEM = {"sans": ("DejaVu Sans", "Helvetica.ttc", "DejaVuSans.ttf"),  # fc-match family, macOS, Linux file
          "mono": ("DejaVu Sans Mono", "Menlo.ttc", "DejaVuSansMono.ttf")}


def read() -> dict:
    """design.json parsed, {} when absent; ValueError when it is not JSON or has the wrong shape."""
    if not DESIGN_JSON.exists():
        return {}
    try:
        data = json.loads(DESIGN_JSON.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"{HELP}: not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"{HELP}: expected a JSON object at the top level, got {type(data).__name__}")
    objects = ("fonts", "colors", "logo", "fonts.weights")
    for key in objects:
        value = data
        for part in key.split("."):
            value = value.get(part, {}) if isinstance(value, dict) else {}
        if not isinstance(value, dict):
            raise ValueError(f"{HELP}: {key} = {value!r}: expected an object")
    return data


@lru_cache(maxsize=1)
def load() -> dict:
    data = read()
    fonts, colors, grain = data.get("fonts", {}), data.get("colors", {}), data.get("grain", GRAIN)
    logos = data.get("logo", {})
    bad = [f"unknown key {k}" for k in sorted(set(data) - {"fonts", "colors", "grain", "logo"})]
    bad += [f"unknown key fonts.{k}" for k in sorted(set(fonts) - FONT_KEYS)]
    family = fonts.get("family", "x")
    if not isinstance(family, str) or not family.strip() or not is_family(family):
        bad.append(f"fonts.family = {family!r}: expected a family name")
    bad += [f"{k} = {v!r}: expected a font file path or a family name" for k, v in font_roles(fonts).items()
            if not isinstance(v, str) or not v.strip()]
    bad += [f"colors.{k} = {v!r}: expected one of {', '.join(COLORS)} as #rrggbb" for k, v in colors.items()
            if k not in COLORS or not re.fullmatch(r"#[0-9a-fA-F]{6}", str(v))]
    bad += [] if isinstance(grain, (int, float)) and grain >= 0 else [f"grain = {grain!r}: expected a number >= 0"]
    bad += [f"unknown key logo.{k}" for k in sorted(set(logos) - set(LOGO_KEYS))]
    bad += [f"logo.{k} = {v!r}: expected an .svg or .png path" for k, v in logos.items()
            if not str(v).lower().endswith((".svg", ".png"))]
    if bad:
        raise ValueError(f"{HELP}: {bad[0]}")
    named = {k: v for k, v in font_roles(fonts).items() if not is_family(v)}
    named.update({f"logo.{k}": v for k, v in logos.items()})
    for key, rel in named.items():
        if not (ROOT / str(rel)).is_file():
            raise FileNotFoundError(f"{key} in {DESIGN_JSON} is {rel!r}, but {ROOT / str(rel)} does not exist")
    return data


def is_family(value) -> bool:
    return not str(value).lower().endswith(FONT_EXT)


def font_roles(fonts: dict) -> dict:
    """{role key: path or family name}; `family` fills regular, bold, italic and bold_italic
    for each of those the file leaves unset."""
    roles = {f"fonts.{k}": v for k, v in fonts.items() if k not in ("weights", "family")}
    if fonts.get("family"):
        roles = {**{f"fonts.{k}": fonts["family"] for k in ("regular", "bold", "italic", "bold_italic")}, **roles}
    roles.update({f"fonts.weights.{w}": v for w, v in fonts.get("weights", {}).items()})
    return roles


@lru_cache(maxsize=1)
def resolved() -> dict:
    """resolved.json when it was built from this design.json, else {}."""
    try:
        data = json.loads(RESOLVED.read_text())
    except (OSError, ValueError):
        return {}
    ok = isinstance(data, dict) and data.get("design_json_sha256") == hashlib.sha256(DESIGN_JSON.read_bytes()).hexdigest()
    return data if ok else {}


def font_path(key: str, value: str) -> str:
    """The file for a role: the path under the project root, or the family's file from resolved.json."""
    if not is_family(value):
        return str(ROOT / value)
    path = resolved().get(key)
    if not isinstance(path, str) or not (ROOT / path).is_file():
        raise FileNotFoundError(f"{key} in {DESIGN_JSON} names the family {value!r}, which {RESOLVED} does not "
                                f"resolve to a file here: run `uv run tools/fonts.py` from the project root {ROOT}")
    return str(ROOT / path)


def color(name: str) -> str:
    return load().get("colors", {}).get(name, COLORS[name])


def grain() -> float:
    return float(load().get("grain", GRAIN))


def font(weight: int = 400, italic: bool = False) -> str:
    """An exact `weights` entry, else `bold` from 600, else `regular`, else the system sans;
    italic first tries `bold_italic` (from 600), then `italic`."""
    roles, bold = font_roles(load().get("fonts", {})), weight >= 600
    chain = ["fonts.bold_italic" if bold else None, "fonts.italic"] if italic else []
    chain += [f"fonts.weights.{weight}", "fonts.bold" if bold else None, "fonts.regular"]
    key = next((k for k in chain if k in roles), None)
    return font_path(key, roles[key]) if key else system("sans")


def luminance(hexstr: str) -> float:
    """WCAG relative luminance of a #rrggbb colour, 0 (black) to 1 (white)."""
    c = [int(hexstr[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def logo(variant: str | None = None) -> Path:
    """The logo file: `on_dark` or `on_light`, else the other one. Without a variant the
    background colour picks: `on_dark` when light ink contrasts more with it (luminance < 0.179)."""
    if variant not in (None, *LOGO_KEYS):
        raise ValueError(f"logo variant {variant!r}: expected one of {', '.join(LOGO_KEYS)}")
    variant = variant or ("on_dark" if luminance(color("background")) < 0.179 else "on_light")
    logos = load().get("logo", {})
    path = logos.get(variant) or logos.get(next(k for k in LOGO_KEYS if k != variant))
    if not path:
        raise FileNotFoundError(f"no logo in {DESIGN_JSON}: name logo.on_dark or logo.on_light "
                                "(README.md, \"Brand\")")
    return ROOT / path


def mono() -> str:
    value = font_roles(load().get("fonts", {})).get("fonts.mono")
    return font_path("fonts.mono", value) if value else system("mono")


@lru_cache(maxsize=None)
def system(kind: str) -> str:
    family, mac, linux = SYSTEM[kind]
    paths = [f"/System/Library/Fonts/{mac}"] if sys.platform == "darwin" else []
    if sys.platform != "darwin" and shutil.which("fc-match"):
        paths.append(subprocess.run(["fc-match", "-f", "%{file}", family], capture_output=True, text=True).stdout)
    paths += [f"/usr/share/fonts/{d}/{linux}" for d in ("truetype/dejavu", "TTF", "dejavu")]
    path = next((p for p in paths if p and Path(p).is_file()), None)
    if path is None:
        raise FileNotFoundError(f"no system font {family}: install it or name a font file in {HELP}")
    return path
