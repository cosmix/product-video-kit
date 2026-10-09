"""Browser and page setup shared by the capture and the probe."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

from playwright.async_api import async_playwright

from webcap.director import INIT_SCRIPT, Director
from webcap.project import product
from webcap.server import start
from webcap.world import World

PORT = 7373
ARGS = [
    "--hide-scrollbars",
    "--enable-unsafe-swiftshader",
    "--use-angle=swiftshader",
    "--disable-features=OverlayScrollbar",
]


@asynccontextmanager
async def session(out_dir, scale: float = 2.0):
    world = product().World()
    runner = await start(product().build_app(world), PORT)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=ARGS)
        try:
            yield world, browser, out_dir, scale
        finally:
            await browser.close()
            await runner.cleanup()


async def open_scene(world: World, browser, out_dir, scene: str, path: str = "/",
                     scale: float = 2.0, preroll: float = 1.5) -> Director:
    """A fresh page on `scene`, warmed up so t = 0 is a settled frame."""
    world.set_scene(scene)
    # The page drops a frame older than the one it holds, so it must load at
    # the start of the pre-roll, not at clip t = 0.
    world.t = -preroll
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        device_scale_factor=scale,
        color_scheme="dark",
        reduced_motion="no-preference",
    )
    storage = json.dumps(getattr(product(), "LOCAL_STORAGE", {}))
    await context.add_init_script(INIT_SCRIPT.replace("__STORAGE__", storage))
    page = await context.new_page()
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    # Python's clock API takes seconds (or datetimes), not milliseconds.
    epoch = world.clock.epoch_ms() / 1000 - preroll - 1.5
    await page.clock.install(time=epoch)
    await page.goto(f"http://127.0.0.1:{PORT}{path}")
    await page.wait_for_load_state("networkidle")
    await page.evaluate("document.fonts.ready.then(() => true)")
    await page.clock.pause_at(epoch + 1.5)
    director = Director(page, world, out_dir, scale)
    director.errors = errors
    await director.setup()
    director.frame = -round(preroll * 60)
    await director.hold(preroll)
    if errors:  # the page's own errors while warming up; clips can check director.errors too
        print(f"page errors in scene {scene!r}: " + " | ".join(errors[-5:]))
    return director
