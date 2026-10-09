"""The edit's self-test (GL context, shaders, design fonts and colours, encoder): the plain
background with one test window, a placeholder clip in browser chrome. It needs no project files.

Usage: uv run bg_test.py [seconds]   -> out/bg_test.mp4
"""

import sys
from pathlib import Path

from editkit.compositor import Compositor, Quality
from editkit.scene import Plane, Segment, Timeline
from render import encoder

OUT = Path(__file__).resolve().parent / "out" / "bg_test.mp4"


def main() -> None:
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0
    q = Quality()
    window = Plane("broll:selftest", 0.0, dur, chrome="browser", title="edit self-test", scale=0.6, fade_in=0.4)
    comp = Compositor(Timeline(dur, [Segment("selftest", 0.0, [window])]), q)
    OUT.parent.mkdir(exist_ok=True)
    enc = encoder(OUT, q, 0.0, dur, None, fast=False)
    for i in range(int(dur * q.fps)):
        enc.stdin.write(comp.render(i / q.fps))
    enc.stdin.close()
    enc.wait()
    comp.close()
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
