"""Skia GPU context, the design-system palette, typography and the reusable
drawing primitives (glow strokes, cards, rules).

Everything is authored in 1920x1080 logical units; the renderer applies a
2x scale before calling a scene, so blur sigmas and strokes stay in
logical pixels."""

import sys
from functools import lru_cache

import moderngl
import skia

from . import design

W, H = 1920, 1080
SS = 2  # supersample factor
MAC = sys.platform == "darwin"


def rgb(hexstr):
    h = hexstr.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def col(hexstr, a=1.0):
    r, g, b = rgb(hexstr)
    return skia.Color4f(r, g, b, max(0.0, min(1.0, a)))


def mixcol(h1, h2, u):
    a, b = rgb(h1), rgb(h2)
    u = max(0.0, min(1.0, u))
    return "#%02x%02x%02x" % tuple(int(round(255 * (a[i] + (b[i] - a[i]) * u))) for i in range(3))


# Palette: the project's design.json (lib/design.py); hairlines and card fills are mixed from it.
BG = design.color("background")
FG = design.color("text")
FG2 = design.color("secondary")
ACCENT = design.color("accent")
HAIR = mixcol(BG, FG, 0.16)  # hairlines, card borders, graph connectors
CARD = mixcol(BG, FG, 0.05)
GLOW = 0.0  # glow multiplier; 0 disables every glow pass


class Gpu:
    """Owns the GL context (EGL on Linux, CGL on macOS) and the two render targets (2x and 1x)."""

    def __init__(self):
        if MAC:  # skia's native interface is CGL's, which moderngl has made current
            self.ctx = moderngl.create_standalone_context(require=330)
            self.gr = skia.GrDirectContext.MakeGL()
        else:  # the native interface is GLX's, so name EGL
            self.ctx = moderngl.create_standalone_context(backend="egl", require=330)
            self.gr = skia.GrDirectContext.MakeGL(skia.GrGLInterface.MakeEGL())
        if self.gr is None:
            raise RuntimeError("skia found no GL context")
        # half-float targets: 8-bit premultiplied pixels lose their colour at low
        # alpha, which shows as blocky fringes once un-premultiplied for ProRes 4444
        info = skia.ImageInfo.Make(W * SS, H * SS, skia.kRGBA_F16_ColorType, skia.kPremul_AlphaType)
        self.big = skia.Surface.MakeRenderTarget(self.gr, skia.Budgeted.kNo, info)
        self.small = skia.Surface.MakeRenderTarget(
            self.gr, skia.Budgeted.kNo, skia.ImageInfo.Make(W, H, skia.kRGBA_F16_ColorType, skia.kPremul_AlphaType)
        )
        if self.big is None or self.small is None:
            raise RuntimeError("GPU surfaces unavailable")

    def frame(self, draw, transparent):
        """Run draw(canvas) at 2x, downsample, return unpremultiplied RGBA bytes."""
        c = self.big.getCanvas()
        c.save()
        if transparent:
            c.clear(skia.Color4f(0, 0, 0, 0))
        else:
            c.clear(col(BG))
        c.scale(SS, SS)
        draw(c)
        c.restore()
        img = self.big.makeImageSnapshot()
        sc = self.small.getCanvas()
        sc.clear(skia.Color4f(0, 0, 0, 0))
        sc.drawImageRect(
            img, skia.Rect.MakeWH(W, H), skia.SamplingOptions(skia.CubicResampler.Mitchell())
        )
        return self.small.makeImageSnapshot().toarray(
            colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kUnpremul_AlphaType
        )


# ---------------------------------------------------------------- typography


@lru_cache(maxsize=None)
def typeface(weight, italic=False):
    path = design.font(weight, italic)
    tf = skia.Typeface.MakeFromFile(path, 0)
    if tf is None:
        raise RuntimeError(f"skia cannot read the font {path}")
    return tf


@lru_cache(maxsize=None)
def font(size, weight=400, italic=False):
    f = skia.Font(typeface(weight, italic), size)
    f.setSubpixel(True)
    f.setEdging(skia.Font.Edging.kSubpixelAntiAlias)
    return f


def text_width(s, size, weight=400, tracking=0.0):
    f = font(size, weight)
    glyphs = f.textToGlyphs(s)
    if not glyphs:
        return 0.0
    return sum(f.getWidths(glyphs)) + tracking * size * (len(glyphs) - 1)


def text(canvas, s, x, y, size, color=FG, weight=400, tracking=0.0, alpha=1.0, align="left", blend=None):
    """Draw a string with optional tracking (em units). Returns its width."""
    if not s or alpha <= 0.001:
        return 0.0
    f = font(size, weight)
    glyphs = f.textToGlyphs(s)
    widths = f.getWidths(glyphs)
    xs, cur = [], 0.0
    for w in widths:
        xs.append(cur)
        cur += w + tracking * size
    total = cur - tracking * size
    if align == "center":
        x -= total / 2
    elif align == "right":
        x -= total
    blob = skia.TextBlob.MakeFromPosTextH(s, [x + v for v in xs], y, f)
    paint = skia.Paint(AntiAlias=True, Color4f=col(color, alpha))
    if blend is not None:
        paint.setBlendMode(blend)
    canvas.drawTextBlob(blob, 0, 0, paint)
    return total


def text_glow(canvas, s, x, y, size, color=ACCENT, weight=400, tracking=0.0, alpha=1.0, sigma=10, align="left"):
    """A soft additive glow under a string."""
    alpha *= GLOW
    if alpha <= 0.001:
        return
    f = font(size, weight)
    glyphs = f.textToGlyphs(s)
    widths = f.getWidths(glyphs)
    xs, cur = [], 0.0
    for w in widths:
        xs.append(cur)
        cur += w + tracking * size
    total = cur - tracking * size
    if align == "center":
        x -= total / 2
    elif align == "right":
        x -= total
    blob = skia.TextBlob.MakeFromPosTextH(s, [x + v for v in xs], y, f)
    p = skia.Paint(AntiAlias=True, Color4f=col(color, alpha))
    p.setImageFilter(skia.ImageFilters.Blur(sigma, sigma))
    p.setBlendMode(skia.BlendMode.kPlus)
    canvas.drawTextBlob(blob, 0, 0, p)


def label(canvas, s, x, y, size=12, color=FG2, alpha=1.0, align="left", weight=500):
    """Small caps-style tracked label."""
    return text(canvas, s.upper(), x, y, size, color, weight, tracking=0.18, alpha=alpha, align=align)


# ---------------------------------------------------------------- primitives


def stroke_paint(color, width, alpha=1.0, cap="round"):
    p = skia.Paint(AntiAlias=True, Color4f=col(color, alpha), StrokeWidth=width, Style=skia.Paint.kStroke_Style)
    p.setStrokeCap(skia.Paint.kRound_Cap if cap == "round" else skia.Paint.kButt_Cap)
    p.setStrokeJoin(skia.Paint.kRound_Join)
    return p


def fill_paint(color, alpha=1.0):
    return skia.Paint(AntiAlias=True, Color4f=col(color, alpha))


def glow_stroke(canvas, path, color, width, sigma, alpha, blur_extra=0.0):
    """Additive glow pass for a path: wide blurred stroke, kPlus blend."""
    alpha *= GLOW
    if alpha <= 0.002:
        return
    p = stroke_paint(color, width, alpha)
    p.setImageFilter(skia.ImageFilters.Blur(sigma + blur_extra, sigma + blur_extra))
    p.setBlendMode(skia.BlendMode.kPlus)
    canvas.drawPath(path, p)


def soft_stroke(canvas, path, color, width, alpha, blur=0.0, cap="round"):
    """Core stroke, optionally defocused (depth of field)."""
    if alpha <= 0.002:
        return
    p = stroke_paint(color, width, alpha, cap)
    if blur > 0.15:
        p.setImageFilter(skia.ImageFilters.Blur(blur, blur))
    canvas.drawPath(path, p)


def glow_dot(canvas, x, y, r, color, alpha, sigma=None):
    alpha *= GLOW
    if alpha <= 0.002:
        return
    p = fill_paint(color, alpha)
    p.setImageFilter(skia.ImageFilters.Blur(sigma if sigma is not None else r * 0.9, sigma if sigma is not None else r * 0.9))
    p.setBlendMode(skia.BlendMode.kPlus)
    canvas.drawCircle(x, y, r, p)


def rrect(x, y, w, h, r):
    return skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x, y, w, h), r, r)


def card(canvas, x, y, w, h, alpha=1.0, accent=None, radius=10, fill=None, border=None, shadow=True, glow=0.0, blur=0.0):
    """Dashboard-style card: soft shadow, translucent fill, hairline, accent bar."""
    if alpha <= 0.002:
        return
    fill = fill or CARD
    border = border or HAIR
    rr = rrect(x, y, w, h, radius)
    if shadow:
        sp = fill_paint("#000000", 0.55 * alpha)
        sp.setImageFilter(skia.ImageFilters.Blur(22, 22))
        canvas.save()
        canvas.translate(0, 10)
        canvas.drawRRect(rr, sp)
        canvas.restore()
    if glow * GLOW > 0.002 and accent:
        gp = fill_paint(accent, 0.35 * glow * alpha * GLOW)
        gp.setImageFilter(skia.ImageFilters.Blur(28, 28))
        gp.setBlendMode(skia.BlendMode.kPlus)
        canvas.drawRRect(rr, gp)
    fp = fill_paint(fill, 0.94 * alpha)
    if blur > 0.15:
        fp.setImageFilter(skia.ImageFilters.Blur(blur, blur))
    canvas.drawRRect(rr, fp)
    bp = stroke_paint(border, 1.0, alpha)
    if blur > 0.15:
        bp.setImageFilter(skia.ImageFilters.Blur(blur, blur))
    canvas.drawRRect(rr, bp)
    if accent:
        canvas.save()
        canvas.clipRRect(rr, True)
        canvas.drawRect(skia.Rect.MakeXYWH(x, y, 3, h), fill_paint(accent, alpha))
        canvas.restore()


def hairline(canvas, x1, y1, x2, y2, alpha=1.0, color=None, width=1.0):
    if alpha <= 0.002:
        return
    canvas.drawLine(x1, y1, x2, y2, stroke_paint(color or HAIR, width, alpha, cap="butt"))


def pill(canvas, s, x, y, color, alpha=1.0, size=11, filled=False):
    """Status pill: tracked small label inside a hairline capsule. Returns width."""
    if alpha <= 0.002:
        return 0.0
    tw = text_width(s.upper(), size, 500, 0.14)
    w, h = tw + 18, size + 10
    rr = rrect(x, y - h + size * 0.28, w, h, h / 2)
    if filled:
        canvas.drawRRect(rr, fill_paint(color, 0.16 * alpha))
    canvas.drawRRect(rr, stroke_paint(color, 1.0, 0.55 * alpha))
    text(canvas, s.upper(), x + 9, y, size, color, 500, tracking=0.14, alpha=alpha)
    return w
