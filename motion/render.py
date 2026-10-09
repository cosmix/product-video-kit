"""render.py <scene> [--duration s] [--alpha] [--variants] [--contact] [--fps n] [--still t]
render.py --selftest

Renders one scene, motion/scenes/<scene>.py (a module defining SCENE, a lib.scene.Scene
subclass), to out/<scene>.mp4 (H.264) or a transparent out/<scene>[_alpha].mov (ProRes 4444)
and updates out/manifest.json with the retimed marks. --selftest renders the kit's own test
scene (a still, a contact sheet and a 2 s clip) to check the GPU and encoder."""

import argparse
import importlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lib import gfx  # noqa: E402
from lib.encode import Writer, contact_sheet, save_png  # noqa: E402

OUT = os.path.join(HERE, "out")
SCENES = os.path.join(HERE, "scenes")


def available():
    return sorted(f[:-3] for f in os.listdir(SCENES) if f.endswith(".py") and not f.startswith("_"))


def load(name, duration):
    if name == "selftest":
        from lib.selftest import SelfTest
        return SelfTest(duration)
    if not os.path.exists(os.path.join(SCENES, f"{name}.py")):
        have = ", ".join(available()) or "none yet"
        sys.exit(f"no scene {name!r}: create motion/scenes/{name}.py defining SCENE, a lib.scene.Scene "
                 f"subclass (README.md, \"Motion graphics\"). Scenes: {have}")
    module = importlib.import_module(f"scenes.{name}")
    if not hasattr(module, "SCENE"):
        sys.exit(f"motion/scenes/{name}.py defines no SCENE (README.md, \"Motion graphics\")")
    return module.SCENE(duration)


def update_manifest(entry):
    path = os.path.join(OUT, "manifest.json")
    data = []
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
    data = [e for e in data if e["file"] != entry["file"]]
    data.append(entry)
    data.sort(key=lambda e: e["file"])
    with open(path, "w") as f:
        json.dump(data, f, indent=1)


def frame_fn(scene, gpu, transparent, handle):
    return lambda t: gpu.frame(lambda c: scene.draw(c, t - handle, not transparent), transparent)


def still(scene, render, t, suffix, over):
    p = os.path.join(OUT, f"{scene.name}{suffix}_{t:05.2f}.png")
    fr = render(t)
    if over:
        import numpy as np
        from PIL import Image
        hexcol = over.lstrip("#")
        bg = Image.new("RGBA", (gfx.W, gfx.H), tuple(int(hexcol[i:i + 2], 16) for i in (0, 2, 4)) + (255,))
        fr = np.array(Image.alpha_composite(bg, Image.fromarray(fr, "RGBA")))
    save_png(fr, p)
    print(p)


def contact(scene, render, dur, suffix):
    times = [dur * (i + 0.5) / 9 for i in range(9)]
    p = os.path.join(OUT, f"{scene.name}{suffix}_contact.png")
    contact_sheet([render(t) for t in times], times, p)
    print(p)


def movie(scene, render, transparent, args):
    h = args.handle
    dur = scene.duration + 2 * h
    ext = "mov" if transparent else "mp4"
    fname = f"{scene.name}{args.suffix}{'_alpha' if transparent and not scene.alpha else ''}.{ext}"
    path = os.path.join(OUT, fname)
    n = int(round(dur * args.fps))
    w = Writer(path, args.fps, transparent)
    t0 = time.time()
    for i in range(n):
        w.write(render(i / args.fps))
        if i % 120 == 0:
            print(f"  {i}/{n} frames  {time.time() - t0:5.1f}s", flush=True)
    w.close()
    update_manifest({
        "scene": scene.name, "key": scene.key, "file": fname, "size": [gfx.W, gfx.H], "fps": args.fps,
        "duration": round(dur, 3), "handle": h, "window": round(scene.duration, 3), "alpha": transparent,
        "marks": [{"t": round(m["t"] + h, 3), "event": m["event"]} for m in scene.scaled_marks()],
    })
    print(f"{path}  {n} frames in {time.time() - t0:.1f}s")


def selftest(gpu, args):
    scene = load("selftest", None)
    render = frame_fn(scene, gpu, False, 0.0)
    print("GL_RENDERER:", gpu.ctx.info["GL_RENDERER"])
    still(scene, render, 1.5, "", None)
    contact(scene, render, scene.duration, "")
    movie(scene, render, False, args)


def parse():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scene", nargs="?", help="a module name in motion/scenes/")
    ap.add_argument("--selftest", action="store_true", help="render the kit's test scene")
    ap.add_argument("--duration", type=float, default=None)
    ap.add_argument("--alpha", action="store_true", help="transparent ProRes 4444 instead of the scene default")
    ap.add_argument("--opaque", action="store_true", help="force opaque H.264")
    ap.add_argument("--variants", action="store_true",
                    help="the scene's default, plus the transparent variant when the default is opaque")
    ap.add_argument("--contact", action="store_true", help="only render a 9-frame contact sheet")
    ap.add_argument("--still", type=float, default=None, help="render one PNG at time t")
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--suffix", default="")
    ap.add_argument("--over", default=None, help="composite --still over this hex colour")
    ap.add_argument("--handle", type=float, default=0.0, help="seconds of hold added before and after the scene window")
    args = ap.parse_args()
    if not args.selftest and not args.scene:
        ap.error(f"name a scene (have: {', '.join(available()) or 'none yet'}) or pass --selftest")
    return args


def main():
    args = parse()
    os.makedirs(OUT, exist_ok=True)
    if args.selftest:
        selftest(gfx.Gpu(), args)
        return
    scene = load(args.scene, args.duration)
    gpu = gfx.Gpu()
    transparent = (scene.alpha or args.alpha) and not args.opaque
    render = frame_fn(scene, gpu, transparent, args.handle)
    if args.still is not None:
        still(scene, render, args.still, args.suffix, args.over)
    elif args.contact:
        contact(scene, render, scene.duration + 2 * args.handle, args.suffix)
    else:
        movie(scene, render, transparent, args)
        if args.variants and not transparent:
            movie(scene, frame_fn(scene, gpu, True, args.handle), True, args)


if __name__ == "__main__":
    main()
