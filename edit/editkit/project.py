"""The project's own edit decision list, edit/edl.py (README.md, "The edit").

It must define `END` (the video's last frame, seconds) and `build() -> editkit.scene.Timeline`;
`BROLL_CLIPS` (b-roll names the cut uses, for credits) and `BUSY` (scene keys where the mix
ducks the melody further) are optional.
"""

import importlib
import sys
from functools import lru_cache
from pathlib import Path

EDIT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def edl():
    if not (EDIT / "edl.py").exists():
        sys.exit(f"no edit decision list: create {EDIT / 'edl.py'} defining END and build() "
                 "(README.md, \"The edit\")")
    if str(EDIT) not in sys.path:
        sys.path.insert(0, str(EDIT))
    module = importlib.import_module("edl")
    missing = [name for name in ("END", "build") if not hasattr(module, name)]
    if missing:
        sys.exit(f"{EDIT / 'edl.py'} lacks {', '.join(missing)} (README.md, \"The edit\")")
    return module
