"""Subtitles from the narration scripts, timed with the whisper word timings.

Usage: uv run subs.py            -> out/intro.srt (nothing for a video without narration)
"""

import difflib
import re
import sys
from pathlib import Path

from editkit.assets import ROOT
from editkit.shots import _words, timeline

OUT = Path(__file__).resolve().parent / "out" / "intro.srt"
MAX_LINE = 42


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9']", "", w.lower())


def _phrases(text: str) -> list[str]:
    """Split at pause tags and sentence ends; long pieces split at the comma nearest the middle."""
    parts = []
    for chunk in re.split(r"<[^>]+>", text):
        parts += [p.strip() for p in re.split(r"(?<=[.?!])\s+", chunk) if p.strip()]
    out = []
    while parts:
        p = parts.pop(0)
        if len(p) <= MAX_LINE * 2:
            out.append(p)
            continue
        breaks = [m.end() for m in re.finditer(r"[,:;]\s", p)] or [m.end() for m in re.finditer(r"\s", p)]
        # no whitespace at all (CJK text): cut by characters at the length limit
        cut = min(breaks, key=lambda c: abs(c - len(p) / 2)) if breaks else MAX_LINE * 2
        parts[:0] = [p[:cut].strip(), p[cut:].strip()]
    return out


def _timed_words(section: str, script_words: list[str]) -> list[tuple[float, float]]:
    """(start, end) for every script word, aligned against whisper's words."""
    if not _words():
        sys.exit("no word timings (edit/build/words.json): run `uv run words.py` first")
    heard = _words().get(section, [])
    if not heard:
        sys.exit(f"no word timings for section {section!r}: run `uv run words.py`, and if it was run, "
                 f"the take produced no words (check narration/final/{section}.wav)")
    a = [_norm(w) for w in script_words]
    b = [_norm(w["w"]) for w in heard]
    times: list = [None] * len(a)
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            h = heard[blk.b + k]
            times[blk.a + k] = (h["start"], h["end"])
    # unmatched words (a compound heard as two words, say): interpolate between neighbours
    for i, t in enumerate(times):
        if t is None:
            prev = next((times[j][1] for j in range(i - 1, -1, -1) if times[j]), heard[0]["start"])
            nxt = next((times[j][0] for j in range(i + 1, len(times)) if times[j]), heard[-1]["end"])
            times[i] = (prev, max(nxt, prev))
    return times


def _wrap(text: str) -> str:
    if len(text) <= MAX_LINE:
        return text
    words = text.split()
    if len(words) < 2:  # one over-long word (a URL) stays on its own line
        return text
    best = min(range(1, len(words)),
               key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return " ".join(words[:best]) + "\n" + " ".join(words[best:])


def _ts(t: float) -> str:
    ms = max(0, int(round(t * 1000)))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def cues() -> list[tuple[float, float, str]]:
    out = []
    for sec in timeline()["narration"]:
        script = ROOT / "narration" / f"{sec['name']}.txt"
        if not script.exists():
            sys.exit(f"no {script.relative_to(ROOT)}: the script for section {sec['name']!r} is missing")
        text = script.read_text()
        phrases = _phrases(text)
        script_words = [w for p in phrases for w in p.split()]
        times = _timed_words(sec["name"], script_words)
        i = 0
        for p in phrases:
            n = len(p.split())
            out.append((max(0.0, times[i][0] - 0.05), times[i + n - 1][1] + 0.35, p))
            i += n
    out.sort()  # inserts sit between sections in time, not in list order
    fixed = []
    for k, (s, e, p) in enumerate(out):
        e = max(e, s + 0.8)  # minimum cue length, but never into the next cue
        if k + 1 < len(out):
            e = max(min(e, out[k + 1][0] - 0.04), s)
        fixed.append((s, e, p))
    return fixed


def main() -> None:
    timed = cues()
    if not timed:
        print("no narration in narration/timeline.json: no subtitles written")
        return
    OUT.parent.mkdir(exist_ok=True)
    lines = []
    for n, (s, e, p) in enumerate(timed, 1):
        lines += [str(n), f"{_ts(s)} --> {_ts(e)}", _wrap(p), ""]
    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT} ({len(timed)} cues)")


if __name__ == "__main__":
    main()
