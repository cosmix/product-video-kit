"""Raster art made with PIL: tracked text, window title bars, the cursor sprite.

Everything is drawn at 2x (or more) of its on-screen size and handed to the GPU with a full
mip chain, so it stays crisp at any scale the camera puts it at.
"""

from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import design


def rgb(hexcol: str) -> tuple:
    return tuple(int(hexcol[i:i + 2], 16) for i in (1, 3, 5))


BACKGROUND = rgb(design.color("background"))
SECONDARY = rgb(design.color("secondary"))
# window chrome: neutral greys
HAIRLINE = (0x3A, 0x3A, 0x3C)
BAR = (0x1C, 0x1C, 0x1E)
DOTS = ((0x4A, 0x4A, 0x4D),) * 3


@lru_cache(maxsize=None)
def font(size: int, weight: int = 400, italic: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(design.font(weight, italic), size)


def tracked_text(text: str, size: int, weight: int, tracking: float, color, pad: int = 4) -> np.ndarray:
    """Text with letter spacing (`tracking` in em) as straight-alpha RGBA."""
    f = font(size, weight)
    advance = f.getlength("M") + tracking * size
    width = int(advance * len(text) - tracking * size) + pad * 2
    asc, desc = f.getmetrics()
    img = Image.new("RGBA", (width, asc + desc + pad * 2), color + (0,))
    d = ImageDraw.Draw(img)
    for i, ch in enumerate(text):
        d.text((pad + i * advance, pad), ch, font=f, fill=color + (255,))
    return np.asarray(img)


def title_bar(kind: str, title: str, width: int, height: int, scale: int = 2) -> np.ndarray:
    """Title bar overlay (dots, title or URL pill) as straight-alpha RGBA, transparent bg."""
    W, H = width * scale, height * scale
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = 6 * scale
    cy = H / 2
    for i, c in enumerate(DOTS):
        cx = (20 + i * 20) * scale
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=c + (255,))
    f = font(14 * scale, 400)
    if kind == "browser":
        pill_w, pill_h = 420 * scale, 26 * scale
        x0 = (W - pill_w) / 2
        d.rounded_rectangle((x0, cy - pill_h / 2, x0 + pill_w, cy + pill_h / 2), radius=pill_h / 2,
                            fill=(0x2A, 0x2A, 0x2C, 255), outline=HAIRLINE + (255,), width=scale)
        text = title or "127.0.0.1:7373"
        tw = d.textlength(text, font=f)
        d.text(((W - tw) / 2, cy), text, font=f, fill=SECONDARY + (255,), anchor="lm")
        # quiet reload glyph at the right of the bar
        gx = W - 28 * scale
        d.arc((gx - 6 * scale, cy - 6 * scale, gx + 6 * scale, cy + 6 * scale), 40, 330,
              fill=(0x6A, 0x6A, 0x6E, 255), width=max(1, int(1.5 * scale)))
    elif title:
        tw = d.textlength(title, font=f)
        d.text(((W - tw) / 2, cy), title, font=f, fill=SECONDARY + (255,), anchor="lm")
    return np.asarray(img)


@lru_cache(maxsize=1)
def cursor_sprite(ss: int = 8) -> tuple[np.ndarray, tuple[float, float], tuple[float, float]]:
    """Stylised arrow pointer. Returns (rgba, size in CSS px, hotspot in sprite uv)."""
    w, h = 28, 34  # CSS px, including room for the shadow
    tip = (4.0, 3.0)
    arrow = [(0, 0), (0, 17.5), (4.3, 13.6), (7.2, 20.2), (9.9, 19.0), (7.1, 12.6), (12.6, 12.6)]
    pts = [((tip[0] + x) * ss, (tip[1] + y) * ss) for x, y in arrow]
    shadow = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(shadow).polygon([(x + 1.0 * ss, y + 2.2 * ss) for x, y in pts], fill=120)
    shadow = shadow.filter(ImageFilter.GaussianBlur(2.2 * ss))
    img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    img.putalpha(shadow)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    core = mask.filter(ImageFilter.MinFilter(2 * round(1.3 * ss) + 1))
    body = Image.new("RGBA", img.size, (0x14, 0x14, 0x14, 0))
    body.putalpha(mask)
    body.paste((0xF5, 0xF5, 0xF5, 255), mask=core)
    img = Image.alpha_composite(img, body)
    img = img.resize((w * 4, h * 4), Image.LANCZOS)
    return np.asarray(img), (float(w), float(h)), (tip[0] / w, tip[1] / h)

