"""Credits as data, read from the workstreams' credit files, for the on-screen credits and the
video description (credits.py).

Credits carry only what a licence requires: CC BY b-roll and CC BY samples. CC0 samples
and the TTS narration need no attribution, and a video without music or b-roll credits none.
Optional rows the human asks for go in edit/credits.json (README.md, "Subtitles and credits"):

    {"title": "<product>: introduction", "rows": [["Narration", "Gemini TTS (<voice>)"]]}
"""

import json
import re
from dataclasses import dataclass

from .assets import ROOT, SOUNDTRACK

CREDITS_JSON = ROOT / "edit" / "credits.json"


@dataclass
class Credit:
    title: str      # the work
    by: str         # author, channel or maker
    licence: str    # short licence name
    url: str = ""


def _settings() -> dict:
    return json.loads(CREDITS_JSON.read_text()) if CREDITS_JSON.exists() else {}


def title() -> str:
    """The first line of CREDITS.txt ("" when credits.json names none)."""
    return _settings().get("title", "")


def extra_rows() -> list[tuple[str, str]]:
    """Optional (label, text) rows from credits.json, in order."""
    return [(label, text) for label, text in _settings().get("rows", [])]


def _md_sections(path) -> dict:
    """'## heading' -> {"Key": "value"} from "- Key: value" lines (continuations folded in)."""
    out, name, last = {}, None, None
    for line in path.read_text().splitlines():
        if line.startswith("## "):
            name, last = line[3:].strip(), None
            out[name] = {}
        elif name and line.startswith("- ") and ":" in line:
            key, val = re.split(r":\s*", line[2:].strip(), maxsplit=1)
            out[name][key] = val
            last = key
        elif name and last and line.startswith("  ") and not line.strip().startswith("-"):
            out[name][last] += " " + line.strip()
    return out


def broll(names: list[str]) -> list[Credit]:
    """The CC BY clips among names; a clip without a CREDITS.md section (generated) needs none."""
    path = ROOT / "broll" / "CREDITS.md"
    if not path.exists():
        return []
    sections = _md_sections(path)
    out = []
    for name in (n for n in names if n in sections):
        s = sections[name]
        title_ = s.get("Title", name)
        if len(title_) >= 100:  # yt-dlp cuts titles at 100 characters: end on a whole word
            title_ = title_.rsplit(" ", 1)[0] + " …"
        out.append(Credit(title_, s.get("Channel", ""), "CC BY", s.get("URL", "")))
    return out


def music_samples() -> list[Credit]:
    """Sample libraries whose licence requires attribution (CC0 ones are left out); none
    without a soundtrack."""
    path = ROOT / "music" / "CREDITS.md"
    if not path.exists() or not SOUNDTRACK.exists():
        return []
    out = []
    for heading, s in _md_sections(path).items():
        source = s.get("Source", "")
        by, _, url = source.partition(",")
        lic = s.get("Licence", "")
        short = re.search(r"\((CC[^)]*)\)", lic) or re.search(r"(CC0 [\d.]+)", lic)
        if short and short.group(1).startswith("CC0"):
            continue
        out.append(Credit(re.sub(r"\s*\(.*\)$", "", heading), by.strip(), short.group(1) if short else lic,
                          url.strip()))
    return out


def lines(broll_clips: list[str]) -> list[str]:
    """The on-screen credit lines: one per credited source, then the optional rows. Pass the
    b-roll clip names the cut uses (the EDL's BROLL_CLIPS)."""
    out = []
    if samples := music_samples():
        out.append("Score with samples from " + "; ".join(f"{c.title} by {c.by}, {c.licence}" for c in samples))
    out += [f"B-roll: {c.title} by {c.by}, {c.licence}" for c in broll(broll_clips)]
    out += [f"{label}: {text}" for label, text in extra_rows()]
    return out
