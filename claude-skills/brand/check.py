#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fonttools==4.65.0",
#     "pillow==12.3.0",
# ]
# ///
"""Check a project's brand files: BRAND.md, brand/ and the design.json made from them.

Usage:
    uv run .claude/skills/brand/check.py [PROJECT_ROOT]

PROJECT_ROOT defaults to the current directory. Prints one line per item, ok / WARN / MISSING,
and exits 1 if anything is MISSING. design.json follows the rules of the project's loaders
(motion/lib/design.py): known keys only, #rrggbb colours, existing font and logo paths. A font
role may name a family instead of a file; tools/fonts.py --check then reports the families it
cannot find and the styles it cannot match exactly.
"""

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image

FONT_KEYS = {"regular", "bold", "italic", "bold_italic", "mono", "weights", "family"}
LOGO_KEYS = {"on_dark", "on_light"}
COLORS = {"background": "#000000", "text": "#ffffff", "secondary": "#a0a0a0", "accent": "#ffffff"}
FOLDERS = {"logo": "SVG, or PNG at least 2000 px wide; on_dark and on_light variants",
           "fonts": "TTF/OTF/TTC files and their licence files (a folder per family)",
           "palette": "optional: exported palette files",
           "reference": "images or videos of the brand in use"}
FONT_EXT = (".ttf", ".otf", ".ttc")
LOGO_EXT = (".svg", ".png")
NUMBER = re.compile(r"\s*([0-9.]+)\s*(px)?\s*")
COUNTS = {"MISSING": 0, "WARN": 0}


def status(level, item, hint=""):
    if level in COUNTS:
        COUNTS[level] += 1
    print(f"{level:<9} {item:<34} {hint}".rstrip())


def font_roles(fonts):
    """{design.json key: value} for every font role; `family` fills the four roles the file leaves unset."""
    roles = {f"fonts.{k}": v for k, v in fonts.items() if k not in ("weights", "family")}
    if fonts.get("family"):
        roles = {**{f"fonts.{k}": fonts["family"] for k in ("regular", "bold", "italic", "bold_italic")}, **roles}
    roles.update({f"fonts.weights.{w}": v for w, v in fonts.get("weights", {}).items()})
    return roles


def is_family(value):
    return not str(value).lower().endswith(FONT_EXT)


def uses_family(root):
    """True when design.json names a font by family; reads leniently, check_design reports the errors."""
    try:
        fonts = json.loads((root / "design.json").read_text()).get("fonts", {})
        return any(is_family(v) for v in font_roles(fonts).values())
    except (OSError, ValueError, AttributeError, TypeError):
        return False


def is_derived(root, path):
    """resolved.json and the files under brand/fonts/.local are made by tools/fonts.py, not brand assets."""
    fonts_dir = root / "brand" / "fonts"
    return fonts_dir in path.parents and (path.relative_to(fonts_dir).parts[0] == ".local" or path == fonts_dir / "resolved.json")


def check_files(root, families):
    if (root / "BRAND.md").is_file():
        status("ok", "BRAND.md")
    else:
        status("MISSING", "BRAND.md", "run the brand skill to write it from BRAND.template.md")
    if not (root / "brand").is_dir():
        status("MISSING", "brand/", "create brand/logo, brand/fonts, brand/palette, brand/reference")
        return
    for name, hint in FOLDERS.items():
        folder = root / "brand" / name
        files = [p for p in folder.rglob("*") if p.is_file() and not is_derived(root, p)] if folder.is_dir() else []
        if not files and name == "fonts" and families:
            status("ok", f"brand/{name}/", "no files: the families are installed on this machine")
        elif files:
            status("ok", f"brand/{name}/", f"{len(files)} file{'s' * (len(files) != 1)}")
        elif name == "palette":
            status("ok", f"brand/{name}/", "empty or absent (optional)")
        else:
            status("WARN", f"brand/{name}/", f"{'empty' if folder.is_dir() else 'absent'}: {hint}")


def schema_errors(data):
    """The loader's rules, as messages; an empty list when design.json is valid."""
    if not isinstance(data, dict):
        return ["expected a JSON object"]
    objects = {k: data.get(k, {}) for k in ("fonts", "colors", "logo")}
    if isinstance(objects["fonts"], dict):
        objects["fonts.weights"] = objects["fonts"].get("weights", {})
    wrong = [f"{k} = {v!r}: expected an object" for k, v in objects.items() if not isinstance(v, dict)]
    if wrong:
        return wrong
    fonts, colors, logos = data.get("fonts", {}), data.get("colors", {}), data.get("logo", {})
    family = fonts.get("family", "x")
    grain = data.get("grain", 0.022)
    bad = [f"unknown key {k}" for k in sorted(set(data) - {"fonts", "colors", "grain", "logo"})]
    bad += [f"unknown key fonts.{k}" for k in sorted(set(fonts) - FONT_KEYS)]
    bad += [] if isinstance(family, str) and family.strip() and is_family(family) else \
        [f"fonts.family = {family!r}: expected a family name"]
    bad += [f"{k} = {v!r}: expected a font file path or a family name" for k, v in font_roles(fonts).items()
            if not isinstance(v, str) or not v.strip()]
    bad += [f"fonts.weights.{w}: the weight must be an integer" for w in fonts.get("weights", {}) if not str(w).isdigit()]
    bad += [f"colors.{k} = {v!r}: expected one of {', '.join(COLORS)} as #rrggbb" for k, v in colors.items()
            if k not in COLORS or not re.fullmatch(r"#[0-9a-fA-F]{6}", str(v))]
    bad += [] if isinstance(grain, (int, float)) and grain >= 0 else [f"grain = {grain!r}: expected a number >= 0"]
    bad += [f"unknown key logo.{k}" for k in sorted(set(logos) - LOGO_KEYS)]
    bad += [f"logo.{k} = {v!r}: expected an .svg or .png path" for k, v in logos.items()
            if not str(v).lower().endswith(LOGO_EXT)]
    return bad


def named_paths(data):
    """{design.json key: relative path} for every font file (not family) and logo file design.json names."""
    named = {k: v for k, v in font_roles(data.get("fonts", {})).items() if not is_family(v)}
    named.update({f"logo.{k}": v for k, v in data.get("logo", {}).items()})
    return {k: str(v) for k, v in named.items()}


def check_design(root):
    """Validate design.json; returns its data, or None when it is absent or invalid."""
    path = root / "design.json"
    if not path.is_file():
        status("MISSING", "design.json", "run the brand skill to generate it from BRAND.md")
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        status("MISSING", "design.json", f"not valid JSON: {e}")
        return None
    bad = schema_errors(data)
    if not bad:  # named_paths reads the shapes schema_errors just vouched for
        bad = [f"{k} is {v!r}, but {root / v} does not exist" for k, v in named_paths(data).items()
               if not (root / v).is_file()]
    for message in bad:
        status("MISSING", "design.json", message)
    if bad:
        return None
    status("ok", "design.json", "keys, colours and paths valid")
    return data


def open_font(path):
    return TTFont(path, fontNumber=0, lazy=True) if path.suffix.lower() == ".ttc" else TTFont(path, lazy=True)


def ascii_advances(font):
    """Advance widths of printable ASCII, and the characters the font lacks."""
    cmap, hmtx = font.getBestCmap(), font["hmtx"]
    chars = [chr(c) for c in range(0x20, 0x7F)]
    return {hmtx[cmap[ord(c)]][0] for c in chars if ord(c) in cmap}, [c for c in chars if ord(c) not in cmap]


def check_font(path, mono):
    """(level, hint) for a font file; the mono font must have one advance width for all ASCII."""
    try:
        with open_font(path) as font:
            family = font["name"].getBestFullName() or path.name
            advances, lacking = ascii_advances(font)
    except Exception as e:  # fontTools raises many types for a damaged file
        return "MISSING", f"does not parse as a font: {e}"
    if not mono:
        return "ok", family
    if lacking:
        return "WARN", f"{family}: mono font lacks ASCII {''.join(lacking[:20])!r}"
    if len(advances) == 1:
        return "ok", f"{family}: monospaced"
    return "MISSING", f"{family}: the mono font is not monospaced ({len(advances)} ASCII advance widths)"


def positive_size(w, h):
    if w <= 0 or h <= 0:
        raise ValueError(f"size {w:g}x{h:g}: width and height must be above zero")
    return w, h


def svg_size(path):
    root = ET.parse(path).getroot()
    if not root.tag.endswith("svg"):
        raise ValueError(f"root element is <{root.tag}>, not <svg>")
    w, h = (NUMBER.fullmatch(root.get(k, "")) for k in ("width", "height"))
    if w and h:
        return positive_size(float(w.group(1)), float(h.group(1)))
    box = (root.get("viewBox") or "").replace(",", " ").split()
    if len(box) == 4:
        return positive_size(float(box[2]), float(box[3]))
    raise ValueError("no viewBox and no numeric width and height")


def check_logo(path):
    """(level, hint) for a logo file: a PNG Pillow reads, or an SVG with a size."""
    try:
        if path.suffix.lower() == ".png":
            with Image.open(path) as im:
                im.verify()
                w, h = im.size
        else:
            w, h = svg_size(path)
    except Exception as e:  # Pillow and the XML parser raise many types for a damaged file
        return "MISSING", f"does not parse: {e}"
    if path.suffix.lower() == ".png" and w < 2000:
        return "WARN", f"PNG {w}x{h}: under 2000 px wide; prefer SVG or a larger export"
    return "ok", f"{path.suffix[1:].upper()} {w:g}x{h:g}"


def check_families(root):
    """Run tools/fonts.py --check in the project: a MISSING line per absent family, a WARN per inexact style."""
    script = root / "tools" / "fonts.py"
    if not script.is_file():
        status("WARN", "font families", f"{script} not found: cannot check families; reinstall the kit")
        return
    try:
        run = subprocess.run(["uv", "run", str(script), "--check"], cwd=root, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as e:
        status("WARN", "font families", f"could not run tools/fonts.py: {e}")
        return
    lines = [m for m in (re.match(r"(WARN|MISSING) ([^:]+): (.*)", line) for line in run.stdout.splitlines()) if m]
    for m in lines:
        status(m.group(1), m.group(2), m.group(3))
    if run.returncode and not any(m.group(1) == "MISSING" for m in lines):
        tail = (run.stderr.strip() or run.stdout.strip()).splitlines()[-1:] or ["no output"]
        status("MISSING", "font families", f"tools/fonts.py --check failed: {tail[0]}")
    elif not lines:
        status("ok", "font families", "found (tools/fonts.py --check)")


def asset_checks(root, data, families):
    """Every font and logo design.json names or brand/ holds. A font in brand/ that design.json
    leaves out is a WARN; a logo is not (a PNG export next to the SVG is normal)."""
    named = named_paths(data) if data else {}
    mono = named.get("fonts.mono")
    found = {str(p.relative_to(root)) for d in ("fonts", "logo") if (root / "brand" / d).is_dir()
             for p in (root / "brand" / d).rglob("*") if p.suffix.lower() in FONT_EXT + LOGO_EXT
             and not is_derived(root, p)}
    for rel in sorted(set(named.values()) | found):
        if not (root / rel).is_file():
            continue
        is_font = rel.lower().endswith(FONT_EXT)
        level, hint = check_font(root / rel, rel == mono) if is_font else check_logo(root / rel)
        if data and level == "ok" and rel not in named.values() and not (families and is_font):
            level, hint = "WARN" if is_font else "ok", f"{hint}; not named in design.json"
        status(level, rel, hint)


def luminance(hexstr):
    c = [int(hexstr[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def check_contrast(data):
    colors = {**COLORS, **data.get("colors", {})}
    bg = luminance(colors["background"])
    for name, floor in (("text", 4.5), ("secondary", 3.0)):
        hi, lo = sorted((bg, luminance(colors[name])), reverse=True)
        ratio = (hi + 0.05) / (lo + 0.05)
        level = "ok" if ratio >= floor else "WARN"
        status(level, f"contrast {name}", f"{ratio:.2f}:1 on {colors['background']} (WCAG floor {floor}:1)")


def check_fresh(root):
    design = root / "design.json"
    sources = [root / "BRAND.md"] if (root / "BRAND.md").is_file() else []
    sources += [p for p in (root / "brand").rglob("*") if p.is_file()] if (root / "brand").is_dir() else []
    newer = sorted(str(p.relative_to(root)) for p in sources if p.stat().st_mtime > design.stat().st_mtime)
    if newer:
        status("WARN", "design.json", f"older than {newer[0]}{f' and {len(newer) - 1} more' if len(newer) > 1 else ''}: rerun the brand skill")
    else:
        status("ok", "design.json", "newer than BRAND.md and brand/")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=".", help="project root (default: current directory)")
    root = Path(ap.parse_args().root).resolve()
    families = uses_family(root)
    check_files(root, families)
    data = check_design(root)
    asset_checks(root, data, families)
    if data is not None and families:
        check_families(root)
    if data is not None:
        check_contrast(data)
    if (root / "design.json").is_file():
        check_fresh(root)
    print(f"\nSummary: {COUNTS['MISSING']} MISSING, {COUNTS['WARN']} WARN")
    sys.exit(1 if COUNTS["MISSING"] else 0)


if __name__ == "__main__":
    main()
