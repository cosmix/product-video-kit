"""Serving helpers for the project's mock server, and a live preview on the wall clock.

The project's fixtures/web/product.py builds an aiohttp application around the product's real
built frontend (README.md, "Web capture"); these helpers do the parts every mock shares.

    uv run python -m webcap.server --scene <name>    # live preview at http://127.0.0.1:7373/
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path

from aiohttp import web


def require_env(name: str, what: str) -> Path:
    """A path taken from the environment; fail with a clear message when it is unset."""
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is not set: {what}")
    return Path(value).expanduser()


def no_store(response: web.StreamResponse) -> web.StreamResponse:
    """Mark a response uncacheable, so a capture never sees a stale API answer."""
    response.headers["Cache-Control"] = "no-store"
    return response


def serve_dist(app: web.Application, dist: Path) -> None:
    """Serve a built single-page frontend: its sub-folders and top-level files as they are,
    every other path as index.html. Add the API routes before calling this."""
    if not (dist / "index.html").exists():
        raise SystemExit(f"{dist} has no index.html: build the product's web frontend first")
    for entry in sorted(dist.iterdir()):
        if entry.is_dir():
            app.router.add_static(f"/{entry.name}", entry)
        elif entry.name != "index.html":
            app.router.add_get(f"/{entry.name}", lambda _r, p=entry: web.FileResponse(p))
    app.router.add_get("/{tail:.*}", lambda _r: web.FileResponse(dist / "index.html"))


async def start(app: web.Application, port: int) -> web.AppRunner:
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    return runner


async def _serve(scene: str, port: int) -> None:
    from webcap.project import product
    world = product().World()
    world.set_scene(scene)
    await start(product().build_app(world), port)
    print(f"http://127.0.0.1:{port}/  (scene {scene}, wall clock; Ctrl-C to stop)")
    origin = time.monotonic()
    while True:
        await world.tick(time.monotonic() - origin)
        await asyncio.sleep(1 / 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the mock in real time, for a look in a browser.")
    parser.add_argument("--scene", required=True, help="a scene name of product.World")
    parser.add_argument("--port", type=int, default=7373)
    args = parser.parse_args()
    asyncio.run(_serve(args.scene, args.port))


if __name__ == "__main__":
    main()
