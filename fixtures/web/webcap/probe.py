"""Quick look: screenshots of a scene at a few clip times, at 1x, for inspection."""

from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

from webcap.browser import open_scene, session


async def run(scene: str, path: str, times: list[float], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    async with session(out) as (world, browser, _, _):
        d = await open_scene(world, browser, out, scene, path, scale=1.0)
        for t in times:
            started = time.monotonic()
            await d.hold(max(0.0, t - d.t))
            shot = out / f"{scene}_{t:05.1f}.png"
            await d.page.screenshot(path=str(shot))
            print(shot, f"{time.monotonic() - started:.1f}s", d.errors[-3:])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scene")
    parser.add_argument("--path", default="/")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("times", type=float, nargs="+")
    args = parser.parse_args()
    asyncio.run(run(args.scene, args.path, args.times, args.out))


if __name__ == "__main__":
    main()
