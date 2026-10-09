"""The renderer's self-test scene (render.py --selftest): a card with text and a few shapes on
the plain ground, in the design file's fonts and colours, so one run exercises skia on the GPU,
the shared GL context and the encoder. It shows nothing of any product, except the project's
logo (lib/logo.py) when design.json names one."""

import skia

from . import design, gfx, logo
from .ease import lerp, seg, smooth
from .scene import Scene


class SelfTest(Scene):
    name = "selftest"
    nominal = 2.0
    marks = [(0.0, "start"), (1.0, "card in"), (2.0, "end")]

    def setup(self):
        # the logo fits a 320x130 box between the card and the rule
        self.logo_w = None
        if design.load().get("logo"):
            _, h = logo.size(320)
            self.logo_w = 320 * min(1.0, 130 / h)

    def draw(self, canvas, t, opaque):
        u = self.u(t)
        s = smooth(seg(u, 0.0, 0.8))
        canvas.drawCircle(lerp(260, 420, s), 400, 70, gfx.fill_paint(gfx.ACCENT, s))
        square = skia.Path()
        square.addRRect(gfx.rrect(300, 560, 220, 220, 24))
        gfx.soft_stroke(canvas, square, gfx.FG2, 4.0, s)
        gfx.hairline(canvas, 220, 860, lerp(220, 1700, s), 860, s)
        a = smooth(seg(u, 0.4, 1.0))
        gfx.card(canvas, 900, 400, 640, 280, a)
        gfx.text(canvas, "Motion self-test", 940, 500, 44, gfx.FG, 700, 0.0, a)
        gfx.text(canvas, "skia, ffmpeg", 940, 560, 26, gfx.FG2, 400, 0.02, a)
        if self.logo_w:
            logo.draw(canvas, 1220, 770, self.logo_w, a)
