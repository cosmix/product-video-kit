"""The project's own capture module, fixtures/web/product.py (README.md, "Web capture").

Required: `World` (a webcap.world.World subclass, constructed with no arguments),
`build_app(world) -> aiohttp.web.Application` (the mock server around the built frontend) and
`CLIPS` ({name: async def clip(world, browser, out_dir, scale) -> (Clip, Page)}). Optional:
`LOCAL_STORAGE` ({key: JSON value} set before every page load, e.g. the UI theme), `THEME` (a
label for the manifest) and `FONT_PROBES` ((scene, path, {label: CSS selector}), reported in
the manifest as the fonts each element rendered with).
"""

from __future__ import annotations

import importlib
import sys
from functools import lru_cache
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]
REQUIRED = ("World", "build_app", "CLIPS")


@lru_cache(maxsize=1)
def product():
    if not (WEB / "product.py").exists():
        sys.exit(f"no capture module: create {WEB / 'product.py'} defining {', '.join(REQUIRED)} "
                 "(README.md, \"Web capture\")")
    if str(WEB) not in sys.path:
        sys.path.insert(0, str(WEB))
    module = importlib.import_module("product")
    missing = [name for name in REQUIRED if not hasattr(module, name)]
    if missing:
        sys.exit(f"{WEB / 'product.py'} lacks {', '.join(missing)} (README.md, \"Web capture\")")
    return module
