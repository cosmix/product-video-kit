"""The project's logo, design.json `logo` (README.md, "Brand"), drawn on a skia canvas.

    logo.draw(canvas, 960, 540, 480)          # centred, 480 px wide, the variant for the background
    w, h = logo.size(480, variant="on_light")

An SVG renders through skia's SVG module: paths, shapes, strokes, fills, gradients, masks,
clip paths, transforms and filters draw. <text>, CSS <style> blocks (class selectors) and
embedded <image> elements draw nothing. For a logo that needs them, convert text to outlines
and styles to attributes, or export a PNG at least 2000 px wide and name that in design.json.
The SVG root needs a viewBox, or a numeric width and height, for its aspect ratio.
A PNG renders through skia.Image with mipmapped sampling."""

import re
import xml.etree.ElementTree as ET
from functools import lru_cache

import skia

from . import design

NUMBER = re.compile(r"\s*([0-9.]+)\s*(px)?\s*")


def positive(path: str, w: float, h: float) -> tuple[float, float]:
    if w <= 0 or h <= 0:
        raise ValueError(f"{path}: the logo size {w:g}x{h:g} must be above zero; fix its width and height or viewBox")
    return w, h


def svg_size(path: str) -> tuple[float, float]:
    """Intrinsic size of an SVG: its numeric width and height, else its viewBox."""
    root = ET.parse(path).getroot()
    w, h = (NUMBER.fullmatch(root.get(k, "")) for k in ("width", "height"))
    if w and h:
        return positive(path, float(w.group(1)), float(h.group(1)))
    box = (root.get("viewBox") or "").replace(",", " ").split()
    if len(box) == 4:
        try:
            size = float(box[2]), float(box[3])
        except ValueError as e:
            raise ValueError(f"{path}: viewBox {root.get('viewBox')!r} is not four numbers") from e
        return positive(path, *size)
    raise ValueError(f"{path}: the <svg> root has no viewBox and no numeric width and height; "
                     "add a viewBox or export a PNG")


@lru_cache(maxsize=None)
def load(path: str):
    """(drawable, width, height) for a logo file: an SVGDOM or an Image, cached per path."""
    if path.lower().endswith(".png"):
        data = skia.Data.MakeFromFileName(path)
        image = skia.Image.MakeFromEncoded(data) if data else None
        if image is None:
            raise RuntimeError(f"skia cannot read the logo {path}")
        return image, image.width(), image.height()
    w, h = svg_size(path)
    dom = skia.SVGDOM.MakeFromStream(skia.FILEStream.Make(path))
    if dom is None:
        raise RuntimeError(f"skia cannot parse the logo {path}; export a PNG at least 2000 px wide instead")
    dom.setContainerSize(skia.Size(w, h))
    return dom, w, h


def size(width: float, variant: str | None = None) -> tuple[float, float]:
    """The drawn size at `width` px wide, aspect kept."""
    _, w, h = load(str(design.logo(variant)))
    return width, width * h / w


def draw(canvas, cx, cy, width, alpha=1.0, variant=None):
    """Draw the logo centred at (cx, cy), scaled to `width` px wide with its aspect kept.
    variant: "on_dark", "on_light", or None to pick by the background (design.logo)."""
    if alpha <= 0:
        return
    item, w, h = load(str(design.logo(variant)))
    s = width / w
    count = canvas.save()
    canvas.translate(cx - width / 2, cy - h * s / 2)
    canvas.scale(s, s)
    # Always clip to the logo's box, so content outside the viewBox never pops in at alpha 1.
    canvas.saveLayerAlpha(skia.Rect.MakeWH(w, h), round(alpha * 255))
    if isinstance(item, skia.Image):
        sampling = skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kLinear)
        canvas.drawImageRect(item, skia.Rect.MakeWH(w, h), sampling)
    else:
        item.render(canvas)
    canvas.restoreToCount(count)
