# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Rebuild narration/timeline.json, the video's clock, from sections.json and the processed takes in final/.

This folder holds the clock even when the video has no voice: a section without a take is silent,
timed by its `duration` or, failing that, by the reading time of its on-screen `text`. A
sections.json with no takes at all builds a timeline with an empty `narration` list and the scene
starts.

usage: uv run build_timeline.py             write timeline.json and print the scene table
       uv run build_timeline.py --sources   print "name take [take2]" per line of sources.json
                                            (process.sh reads it; nothing without sources.json)

sections.json (README.md, "Narration"):
  {"first_start": 2.5, "tail": 3.8,
   "sections": [{"name": "01_open", "style": "...", "gap": 0.0},
                {"name": "02_pitch", "gap": 6.6, "pin": 28.15, "scene_start": 27.9},
                {"name": "03_demo", "duration": 12.0},
                {"name": "04_close", "text": "Try it today. example.com"},
                {"name": "01b_intro", "insert": 25.0}]}
Sections play in list order, the first at `first_start`, each later one after `gap` seconds of
silence (default 0.5); `pin` fixes a section start, `scene_start` a scene start, and `insert`
places a line at a fixed time without adding a scene or shifting anything. A section's length is
its take in final/ if there is one, else `duration`, else the reading time of `text`. A scene's
key is `key`, else the name after its first "_".
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Reading time of on-screen text: max(min_hold, len(text) / reading_cps + pad). About 15
# characters per second is the common subtitle guideline for comfortable reading; min_hold keeps
# a short title up long enough to register; pad covers the text entering and settling.
# sections.json may override each at its top level.
READING = {"reading_cps": 15.0, "min_hold": 2.5, "pad": 1.0}


def read(name: str) -> dict | list:
    path = HERE / name
    if not path.exists():
        sys.exit(f"no {path}: see README.md, \"Narration\"")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"{path}: not valid JSON: {e}")


def take(name: str) -> Path:
    return HERE / "final" / f"{name}.wav"


def number(value: object, where: str, positive: bool = True) -> float:
    """`value` as a float, or exit naming `where` (e.g. "section '02_pitch': duration")."""
    ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not ok or (value <= 0 if positive else value < 0):
        sys.exit(f"{where} = {value!r}: expected a number {'> 0' if positive else '>= 0'}")
    return float(value)


def duration(name: str) -> float:
    path = take(name)
    if not path.exists():
        sys.exit(f"no {path}: point sources.json at a take for {name!r}, then run ./process.sh")
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    except FileNotFoundError:
        sys.exit(f"cannot measure {path}: ffprobe not found; install ffmpeg (it ships ffprobe)")
    try:
        if out.returncode:
            raise ValueError
        return number(float(out.stdout), f"duration of {path}")
    except ValueError:
        sys.exit(f"cannot measure {path}: ffprobe gave {out.stdout.strip() or out.stderr.strip()!r}; "
                 "the take is unreadable or not audio, record or process it again")


def validate(spec: object) -> None:
    """Exit with a message naming the section and field for a sections.json that cannot build."""
    where = HERE / "sections.json"
    if not isinstance(spec, dict) or not isinstance(spec.get("sections"), list):
        sys.exit(f"{where}: expected an object with a \"sections\" list (README.md, \"Narration\")")
    for k in READING:
        if k in spec:
            number(spec[k], f"{where}: {k}")
    for i, sec in enumerate(spec["sections"], 1):
        if not isinstance(sec, dict) or not isinstance(sec.get("name"), str) or not sec["name"]:
            sys.exit(f"{where}: section #{i} has no \"name\"")
        label = f"{where}: section {sec['name']!r}: "
        if "duration" in sec:
            number(sec["duration"], label + "duration")
        for k in ("gap", "pin", "insert", "scene_start"):
            if k in sec:
                number(sec[k], label + k, positive=False)
        if "text" in sec and not isinstance(sec["text"], str):
            sys.exit(f"{label}text = {sec['text']!r}: expected a string")


def length(sec: dict, spec: dict) -> tuple[float, str]:
    """A section's length and where it came from: "take", "duration" or "est" (from `text`)."""
    if take(sec["name"]).exists():
        return duration(sec["name"]), "take"
    if "duration" in sec:
        return float(sec["duration"]), "duration"
    if "text" in sec:
        r = {k: float(spec.get(k, v)) for k, v in READING.items()}
        chars = len(" ".join(sec["text"].split()))  # whitespace runs (newlines too) count once
        return max(r["min_hold"], chars / r["reading_cps"] + r["pad"]), "est"
    sys.exit(f"section {sec['name']!r} has no length: record a take ({take(sec['name'])}, through "
             "sources.json and ./process.sh), set \"duration\", or give its on-screen \"text\"")


def entry(name: str, start: float, end: float) -> dict:
    return {"name": name, "file": f"narration/final/{name}.wav", "start": round(start, 3), "end": round(end, 3)}


def place(spec: dict) -> list[dict]:
    """Every section that starts a scene, with its slot and the slot's source."""
    t, rows = float(spec.get("first_start", 2.5)), []
    for sec in (s for s in spec["sections"] if "insert" not in s):
        t = round(sec.get("pin", t + sec.get("gap", 0.5) if rows else t), 3)
        if rows and t < rows[-1]["end"]:
            sys.exit(f"section {sec['name']!r}: pin {t} is before the previous section "
                     f"{rows[-1]['sec']['name']!r} ends ({rows[-1]['end']}); move the pin later or shorten that section")
        dur, source = length(sec, spec)
        end = round(t + dur, 3)
        mid = 0.0 if not rows else round((rows[-1]["end"] + t) / 2, 2)
        rows.append({"sec": sec, "start": t, "end": end, "source": source,
                     "scene_start": sec.get("scene_start", mid)})
        t = end
    if not rows:
        sys.exit(f"{HERE / 'sections.json'} lists no sections outside inserts")
    return rows


def build(spec: dict, rows: list[dict]) -> dict:
    lines = [entry(r["sec"]["name"], r["start"], r["end"]) for r in rows if r["source"] == "take"]
    scenes = [{"scene": i, "key": r["sec"].get("key", r["sec"]["name"].split("_", 1)[-1]),
               "name": r["sec"]["name"], "start": r["scene_start"]} for i, r in enumerate(rows, 1)]
    inserts = [dict(entry(s["name"], s["insert"], s["insert"] + duration(s["name"])), insert=True)
               for s in spec["sections"] if "insert" in s]
    narration = sorted(lines + inserts, key=lambda s: s["start"])
    total = round(max(s["end"] for s in rows + narration) + spec.get("tail", 3.8), 2)
    return {"total": total, "narration": narration, "scenes": scenes}


def main() -> None:
    if sys.argv[1:] == ["--sources"]:
        if not (HERE / "sources.json").exists():
            print("no sources.json: no narrated takes to process", file=sys.stderr)
            return
        for name, take_ in read("sources.json").items():
            print(name, *(take_ if isinstance(take_, list) else [take_]))
        return
    spec = read("sections.json")
    validate(spec)
    rows = place(spec)
    tl = build(spec, rows)
    (HERE / "timeline.json").write_text(json.dumps(tl, indent=1) + "\n")
    marks = {"take": "", "duration": "silent", "est": "silent ~est (from text: confirm at review)"}
    for r, sc in zip(rows, tl["scenes"]):
        print(f'{sc["scene"]:>2} scene@{sc["start"]:>6}  {sc["name"]:<15} {r["start"]:>7} - {r["end"]:>7}  '
              f'({r["end"] - r["start"]:.2f}s) {marks[r["source"]]}'.rstrip())
    print("total", tl["total"])


if __name__ == "__main__":
    main()
