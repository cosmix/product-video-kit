"""Procedural box-drawing, block and braille glyphs so lines join across cells.

Fonts draw each box glyph inside its own advance with side bearings and hinting
of their own; at 2x the seams between neighbouring cells show. These are drawn
as exact rectangles on the cell grid instead.
"""

from __future__ import annotations

import unicodedata

import skia

LIGHT, HEAVY, DOUBLE = 1, 2, 3
_WEIGHTS = {"LIGHT": LIGHT, "SINGLE": LIGHT, "HEAVY": HEAVY, "DOUBLE": DOUBLE}
_DIRS = {
    "UP": ("u",), "DOWN": ("d",), "LEFT": ("l",), "RIGHT": ("r",),
    "HORIZONTAL": ("l", "r"), "VERTICAL": ("u", "d"),
}
_DASHES = {"DOUBLE": 2, "TRIPLE": 3, "QUADRUPLE": 4}


def _parse_box(name: str) -> dict | None:
    """Arms and weights from a 'BOX DRAWINGS ...' Unicode name."""
    words = name.removeprefix("BOX DRAWINGS ").split()
    if "DIAGONAL" in words:
        return None
    if "ARC" in words:
        dirs = [w for w in words if w in ("UP", "DOWN", "LEFT", "RIGHT")]
        return {"arc": tuple(_DIRS[d][0] for d in dirs)}
    if "DASH" in words:
        count = next(_DASHES[w] for w in words if w in _DASHES)
        weight = HEAVY if "HEAVY" in words else LIGHT
        axis = "h" if "HORIZONTAL" in words else "v"
        return {"dash": (count, weight, axis)}
    arms: dict[str, int] = {}
    prefix = words[0] in _WEIGHTS
    pending: list[str] = []
    weight = None
    for word in words:
        if word == "AND":
            continue
        if word in _WEIGHTS:
            if prefix:
                weight = _WEIGHTS[word]
            else:
                for arm in pending:
                    arms[arm] = _WEIGHTS[word]
                pending = []
        elif word in _DIRS:
            for arm in _DIRS[word]:
                if prefix:
                    arms[arm] = weight or LIGHT
                else:
                    pending.append(arm)
    for arm in pending:
        arms[arm] = LIGHT
    return {"arms": arms} if arms else None


class Procedural:
    """Draws the glyphs it claims; `claims(ch)` says which ones."""

    def __init__(self, cw: float, ch: float):
        self.cw, self.ch = cw, ch
        self.light = max(2, round(cw * 0.105))
        self.heavy = self.light * 2
        self._cache: dict[str, dict | None] = {}

    def claims(self, char: str) -> bool:
        cp = ord(char)
        if 0x2500 <= cp <= 0x257F:
            return self._spec(char) is not None
        return 0x2580 <= cp <= 0x259F or 0x2800 <= cp <= 0x28FF

    def _spec(self, char: str) -> dict | None:
        if char not in self._cache:
            try:
                self._cache[char] = _parse_box(unicodedata.name(char))
            except ValueError:
                self._cache[char] = None
        return self._cache[char]

    def draw(self, canvas: skia.Canvas, char: str, x: float, y: float, paint: skia.Paint) -> None:
        cp = ord(char)
        if 0x2800 <= cp <= 0x28FF:
            self._braille(canvas, cp - 0x2800, x, y, paint)
        elif 0x2580 <= cp <= 0x259F:
            self._block(canvas, cp, x, y, paint)
        else:
            spec = self._spec(char)
            if "arc" in spec:
                self._arc(canvas, spec["arc"], x, y, paint)
            elif "dash" in spec:
                self._dash(canvas, *spec["dash"], x, y, paint)
            else:
                self._arms(canvas, spec["arms"], x, y, paint)

    # -- lines -----------------------------------------------------------
    def _band(self, center: float, thickness: int) -> tuple[float, float]:
        start = round(center - thickness / 2)
        return start, start + thickness

    def _arms(self, canvas, arms: dict[str, int], x, y, paint) -> None:
        cw, ch = self.cw, self.ch
        cx, cy = x + cw / 2, y + ch / 2
        horiz = max((arms.get(a, 0) for a in "lr" if arms.get(a) != DOUBLE), default=0)
        vert = max((arms.get(a, 0) for a in "ud" if arms.get(a) != DOUBLE), default=0)
        for arm, weight in arms.items():
            if weight == DOUBLE:
                gap = self.light
                for offset in (-gap, gap):
                    self._single_arm(canvas, arm, LIGHT, x, y, cx + offset, cy + offset, paint,
                                     overlap=gap + self.light)
                continue
            # Extend across the centre by the crossing line's half-thickness so joins close.
            cross = vert if arm in "lr" else horiz
            overlap = (self.heavy if cross == HEAVY else self.light) / 2 if cross else 0
            if any(w == DOUBLE for w in arms.values()):
                overlap = self.light * 1.5
            self._single_arm(canvas, arm, weight, x, y, cx, cy, paint, overlap)

    def _single_arm(self, canvas, arm, weight, x, y, cx, cy, paint, overlap) -> None:
        t = self.heavy if weight == HEAVY else self.light
        if arm in "lr":
            top, bottom = self._band(cy, t)
            if arm == "l":
                rect = skia.Rect.MakeLTRB(x, top, round(cx + overlap), bottom)
            else:
                rect = skia.Rect.MakeLTRB(round(cx - overlap), top, x + self.cw, bottom)
        else:
            left, right = self._band(cx, t)
            if arm == "u":
                rect = skia.Rect.MakeLTRB(left, y, right, round(cy + overlap))
            else:
                rect = skia.Rect.MakeLTRB(left, round(cy - overlap), right, y + self.ch)
        canvas.drawRect(rect, paint)

    def _dash(self, canvas, count, weight, axis, x, y, paint) -> None:
        t = self.heavy if weight == HEAVY else self.light
        span = self.cw if axis == "h" else self.ch
        period = span / count
        length = period * 0.58
        for i in range(count):
            start = i * period + (period - length) / 2
            if axis == "h":
                top, bottom = self._band(y + self.ch / 2, t)
                canvas.drawRect(skia.Rect.MakeLTRB(x + start, top, x + start + length, bottom), paint)
            else:
                left, right = self._band(x + self.cw / 2, t)
                canvas.drawRect(skia.Rect.MakeLTRB(left, y + start, right, y + start + length), paint)

    def _arc(self, canvas, dirs, x, y, paint) -> None:
        cw, ch = self.cw, self.ch
        left, right = self._band(x + cw / 2, self.light)
        top, bottom = self._band(y + ch / 2, self.light)
        cx, cy = (left + right) / 2, (top + bottom) / 2
        ex = x if "l" in dirs else x + cw
        ey = y if "u" in dirs else y + ch
        path = skia.Path()
        path.moveTo(cx, ey)
        path.arcTo(cx, cy, ex, cy, cw / 2)
        path.lineTo(ex, cy)
        stroke = skia.Paint(paint)
        stroke.setStyle(skia.Paint.kStroke_Style)
        stroke.setStrokeWidth(self.light)
        stroke.setStrokeCap(skia.Paint.kButt_Cap)
        canvas.drawPath(path, stroke)

    # -- blocks ----------------------------------------------------------
    def _block(self, canvas, cp, x, y, paint) -> None:
        cw, ch = self.cw, self.ch
        rects: list[tuple[float, float, float, float]] = []
        alpha = 1.0
        if cp == 0x2580:
            rects = [(0, 0, 1, 0.5)]
        elif 0x2581 <= cp <= 0x2588:
            frac = (cp - 0x2580) / 8
            rects = [(0, 1 - frac, 1, 1)]
        elif 0x2589 <= cp <= 0x258F:
            frac = (0x2590 - cp) / 8
            rects = [(0, 0, frac, 1)]
        elif cp == 0x2590:
            rects = [(0.5, 0, 1, 1)]
        elif 0x2591 <= cp <= 0x2593:
            rects, alpha = [(0, 0, 1, 1)], (cp - 0x2590) * 0.25
        elif cp == 0x2594:
            rects = [(0, 0, 1, 1 / 8)]
        elif cp == 0x2595:
            rects = [(7 / 8, 0, 1, 1)]
        else:
            quads = {
                0x2596: "3", 0x2597: "4", 0x2598: "1", 0x2599: "134", 0x259A: "14",
                0x259B: "123", 0x259C: "124", 0x259D: "2", 0x259E: "23", 0x259F: "234",
            }[cp]
            spots = {"1": (0, 0), "2": (0.5, 0), "3": (0, 0.5), "4": (0.5, 0.5)}
            rects = [(spots[q][0], spots[q][1], spots[q][0] + 0.5, spots[q][1] + 0.5) for q in quads]
        fill = skia.Paint(paint)
        fill.setAlphaf(paint.getAlphaf() * alpha)
        for l, t, r, b in rects:
            canvas.drawRect(skia.Rect.MakeLTRB(round(x + l * cw), round(y + t * ch),
                                               round(x + r * cw), round(y + b * ch)), fill)

    def _braille(self, canvas, bits, x, y, paint) -> None:
        cw, ch = self.cw, self.ch
        radius = cw * 0.12
        order = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (0, 3), (1, 3)]
        for bit, (col, row) in enumerate(order):
            if bits & (1 << bit):
                cx = x + cw * (0.3 + 0.4 * col)
                cy = y + ch * (0.2 + 0.2 * row)
                canvas.drawCircle(cx, cy, radius, paint)

