"""The `tuicap` command: capture the project's terminal clips into captures/tui/.

    uv run tuicap                  # every clip in fixtures/tui/product.py CLIPS
    uv run tuicap --only <name>    # just those, keeping the rest of manifest.json
    uv run tuicap --selftest       # render a canned terminal clip; needs no product

The project's fixtures/tui/product.py (README.md, "TUI capture") defines CLIPS,
{name: function() -> (Recording, marks)}. Optional: prepare() (build the fixture workspace;
runs before capturing), STILL_T ({name: seconds} for the still; default the last frame),
TRUECOLOR ({hex: palette hex}, see palette.py), SOURCE and NOTES (manifest text).
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path

from . import palette
from .capture import prompt, synth_cli
from .render import Recording, render_recording

FIXTURE = Path(__file__).resolve().parents[2]
OUT = FIXTURE.parent.parent / "captures" / "tui"


@lru_cache(maxsize=1)
def product():
    if not (FIXTURE / "product.py").exists():
        sys.exit(f"no capture module: create {FIXTURE / 'product.py'} defining CLIPS "
                 "(README.md, \"TUI capture\")")
    if str(FIXTURE) not in sys.path:
        sys.path.insert(0, str(FIXTURE))
    module = importlib.import_module("product")
    if not hasattr(module, "CLIPS"):
        sys.exit(f"{FIXTURE / 'product.py'} defines no CLIPS (README.md, \"TUI capture\")")
    return module


def _render(job: tuple[str, Recording, list[dict], Path, float | None, dict]) -> dict:
    name, rec, marks, out, still_t, truecolor = job
    palette.TRUECOLOR.update(truecolor)  # workers may start fresh (spawn on macOS)
    still_t = rec.duration - 0.05 if still_t is None else still_t
    info = render_recording(rec, out / f"{name}.mp4", out / f"{name}.png", still_t)
    return {"file": f"{name}.mp4", "still": f"{name}.png", "still_t": round(still_t, 3), **info, "marks": marks}


def selftest() -> None:
    out = OUT.parent / "tui-selftest"
    out.mkdir(parents=True, exist_ok=True)
    output = "".join(f"\x1b[3{1 + i % 6}mline {i + 1}: box ─│┌┐└┘ block ▁▂▃▄▅▆▇█ braille ⣿⡇\x1b[0m\n"
                     for i in range(8)).encode()
    rec, marks = synth_cli(prompt("~/selftest"), "print-test-pattern", output, 80, 14, seed=1)
    clip = _render(("selftest", rec, marks, out, None, {}))
    print(f"{out / clip['file']}: {clip['duration']}s {clip['size'][0]}x{clip['size'][1]}")


def capture(names: list[str] | None) -> None:
    mod = product()
    unknown = set(names or ()) - set(mod.CLIPS)
    if unknown:
        sys.exit(f"unknown clip(s): {', '.join(sorted(unknown))} (have {', '.join(mod.CLIPS)})")
    OUT.mkdir(parents=True, exist_ok=True)
    if hasattr(mod, "prepare"):
        mod.prepare()
    truecolor = getattr(mod, "TRUECOLOR", {})
    still = getattr(mod, "STILL_T", {})
    jobs = [(name, *mod.CLIPS[name](), OUT, still.get(name), truecolor) for name in names or list(mod.CLIPS)]
    with ProcessPoolExecutor(max_workers=len(jobs)) as pool:
        clips = list(pool.map(_render, jobs))
    path = OUT / "manifest.json"
    if names and path.exists():
        fresh = {clip["file"] for clip in clips}
        clips += [clip for clip in json.loads(path.read_text())["clips"] if clip["file"] not in fresh]
    clips.sort(key=lambda clip: clip["file"])
    manifest = {"source": getattr(mod, "SOURCE", ""), "notes": list(getattr(mod, "NOTES", [])), "clips": clips}
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    for clip in clips:
        print(f"{clip['file']}: {clip['duration']}s {clip['size'][0]}x{clip['size'][1]} grid {clip['grid']}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="tuicap", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="+", metavar="NAME")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        selftest()
    else:
        capture(args.only)
