"""Capture the project's web clips (fixtures/web/product.py CLIPS), stills and manifest.

    uv run python -m webcap.capture                  # all clips, 3840x2160, into captures/web/
    uv run python -m webcap.capture <clip> --draft   # one clip at 1x, fast encode, to check choreography
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from webcap.browser import open_scene, session
from webcap.director import FPS
from webcap.project import product

OUT = Path(__file__).resolve().parents[3] / "captures/web"


async def fonts_in_use(world, browser, out) -> dict:
    """Which font files the page actually rendered with, per product.FONT_PROBES selector."""
    probes = getattr(product(), "FONT_PROBES", None)
    if not probes:
        return {}
    scene, path, selectors = probes
    d = await open_scene(world, browser, out, scene, path, 1.0)
    cdp = await d.page.context.new_cdp_session(d.page)
    await cdp.send("DOM.enable")
    await cdp.send("CSS.enable")
    root = (await cdp.send("DOM.getDocument", {"depth": -1}))["root"]["nodeId"]
    report = {}
    for label, selector in selectors.items():
        node = (await cdp.send("DOM.querySelector", {"nodeId": root, "selector": selector}))["nodeId"]
        if not node:
            report[label] = "not found"
            continue
        fonts = await cdp.send("CSS.getPlatformFontsForNode", {"nodeId": node})
        report[label] = {f["familyName"]: f["glyphCount"] for f in fonts["fonts"]}
    await d.page.context.close()
    return report


async def run(names: list[str], draft: bool, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    scale = 1.0 if draft else 2.0
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"clips": {}}
    async with session(out, scale) as (world, browser, _, _):
        manifest["fonts"] = await fonts_in_use(world, browser, out)
        print("fonts:", manifest["fonts"])
        for name in names:
            started = time.monotonic()
            clip, page = await product().CLIPS[name](world, browser, out, scale)
            # A page left open keeps its sockets, and the world keeps sending to them.
            await page.context.close()
            duration = round(clip.frames / FPS, 3)
            manifest["clips"][clip.path.name] = {
                "file": clip.path.name,
                "size": [int(1920 * scale), int(1080 * scale)],
                "fps": FPS,
                "frames": clip.frames,
                "duration": duration,
                "theme": getattr(product(), "THEME", ""),
                "key_marks": {m["event"]: m["t"] for m in clip.marks if m.get("key")},
                "marks": clip.marks,
                "stills": clip.stills,
                "cursor_space": "CSS px of the 1920x1080 viewport; one sample per frame",
                "cursor": clip.cursor,
            }
            print(f"{clip.path.name}: {clip.frames} frames, {duration}s, "
                  f"captured in {time.monotonic() - started:.0f}s", flush=True)
            # Written after every clip: the edit reads it while the rest render.
            partial = manifest_path.with_suffix(".tmp.json")
            partial.write_text(json.dumps(manifest, indent=1))
            partial.replace(manifest_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    clips = product().CLIPS
    parser.add_argument("clips", nargs="*", help=f"any of {', '.join(clips)} (default: all)")
    parser.add_argument("--draft", action="store_true", help="1x, fast encode, into --out")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    unknown = set(args.clips) - set(clips)
    if unknown:
        parser.error(f"unknown clip(s): {', '.join(sorted(unknown))}")
    asyncio.run(run(args.clips or list(clips), args.draft, args.out))


if __name__ == "__main__":
    main()
