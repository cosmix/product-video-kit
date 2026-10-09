"""The credit line: a transparent full-frame card, drawn at 2x with PIL and written to
build/art/ so the EDL can place it like any other still.

One or a few quiet lines in the regular weight and the secondary tone, each centred, the block
centred vertically. No heading, rule or label.
"""

from PIL import Image, ImageDraw

from .art import SECONDARY, font
from .assets import BUILD

S = 2                      # drawing scale (design px -> image px)
W, H = 1920, 1080
PITCH = 34                 # line pitch, design px


def _write(name: str, canvas: Image.Image) -> str:
    out = BUILD / "art" / f"{name}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return f"image:{name}"


def credit_line(name: str, lines: list[str]) -> str:
    f = font(22 * S, 400)
    canvas = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    y0 = H / 2 - (len(lines) - 1) * PITCH / 2
    for i, text in enumerate(lines):
        d.text((W * S / 2, (y0 + i * PITCH) * S), text, font=f, fill=SECONDARY + (255,), anchor="mm")
    return _write(name, canvas)
