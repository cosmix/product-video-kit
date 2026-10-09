"""Replay a recorded byte stream through pyte and render 60 fps frames with skia."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pyte
import skia
from wcwidth import wcwidth

from . import design, palette
from .glyphs import Procedural

# Glyphs the terminal font lacks, in order of preference; a missing file is skipped.
if sys.platform == "darwin":
    FALLBACK_FONTS = ["/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Apple Symbols.ttf"]
    EMOJI_FONT = "/System/Library/Fonts/Apple Color Emoji.ttc"
else:
    FALLBACK_FONTS = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansSymbols-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansMath-Regular.ttf",
    ]
    EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

FPS = 60
CELL_W = 28  # px at 2x; the font size makes one advance fill a cell
CELL_H = 58
PAD = 48  # 24 px at 1x


class VtScreen(pyte.Screen):
    """pyte screen with the pieces a tmux client needs: SU/SD scrolling and the
    private DSR query (CSI ? 6 n), neither of which pyte 0.8 handles."""

    def report_device_status(self, *args, **kwargs) -> None:
        kwargs.pop("private", None)
        super().report_device_status(*args, **kwargs)

    def _scroll_region(self, count: int | None, insert: bool, **_: object) -> None:
        top = self.margins.top if self.margins else 0
        x, y = self.cursor.x, self.cursor.y
        self.cursor.y = top
        (self.insert_lines if insert else self.delete_lines)(count or 1)
        self.cursor.x, self.cursor.y = x, y

    def scroll_up(self, count: int | None = None, **kwargs: object) -> None:
        self._scroll_region(count, insert=False)

    def scroll_down(self, count: int | None = None, **kwargs: object) -> None:
        self._scroll_region(count, insert=True)


class VtStream(pyte.ByteStream):
    csi = {**pyte.ByteStream.csi, "S": "scroll_up", "T": "scroll_down"}


@dataclass
class Geometry:
    cols: int
    rows: int

    @property
    def size(self) -> tuple[int, int]:
        w = self.cols * CELL_W + 2 * PAD
        h = self.rows * CELL_H + 2 * PAD
        return w + (w % 2), h + (h % 2)


class Fonts:
    def __init__(self) -> None:
        mono = design.mono()
        typeface = skia.Typeface.MakeFromFile(mono, 0)
        if typeface is None:
            raise RuntimeError(f"skia cannot read the terminal font {mono}")
        size = CELL_W / (skia.Font(typeface, 100).measureText("M") / 100)

        def load(path: str | Path, bold: bool = False, italic: bool = False) -> skia.Font:
            font = skia.Font(skia.Typeface.MakeFromFile(str(path), 0), size)
            font.setEdging(skia.Font.Edging.kAntiAlias)
            font.setSubpixel(True)
            font.setHinting(skia.FontHinting.kNone)
            font.setLinearMetrics(True)
            font.setEmbolden(bold)  # one font file: bold and italic are synthesised
            font.setSkewX(-0.2 if italic else 0.0)
            return font

        self.variants = {(b, i): load(mono, b, i) for b in (False, True) for i in (False, True)}
        self.fallbacks = [load(p) for p in FALLBACK_FONTS if Path(p).is_file()]
        self.emoji = load(EMOJI_FONT) if Path(EMOJI_FONT).is_file() else None
        metrics = self.variants[(False, False)].getMetrics()
        self.baseline = (CELL_H - (metrics.fDescent - metrics.fAscent)) / 2 - metrics.fAscent
        self._choice: dict[tuple[str, bool, bool], tuple[skia.Font, bool]] = {}

    def pick(self, char: str, bold: bool, italic: bool) -> tuple[skia.Font, bool]:
        """(font, is_primary) for a character, walking the fallback chain."""
        key = (char, bold, italic)
        if key not in self._choice:
            primary = self.variants[(bold, italic)]
            cp = ord(char)
            if primary.unicharToGlyph(cp):
                self._choice[key] = (primary, True)
            else:
                chosen = next((f for f in self.fallbacks if f.unicharToGlyph(cp)), None)
                if chosen is None and self.emoji is not None and self.emoji.unicharToGlyph(cp):
                    chosen = self.emoji
                self._choice[key] = (chosen or primary, False)
        return self._choice[key]


class TerminalRenderer:
    def __init__(self, geometry: Geometry):
        self.geo = geometry
        self.width, self.height = geometry.size
        self.fonts = Fonts()
        self.proc = Procedural(CELL_W, CELL_H)
        self.surface = skia.Surface.MakeRaster(
            skia.ImageInfo.Make(self.width, self.height, skia.kRGBA_8888_ColorType,
                                skia.kPremul_AlphaType))
        self.base: skia.Image | None = None
        self._paints: dict[tuple[str, float], skia.Paint] = {}

    def paint(self, hexval: str, alpha: float = 1.0) -> skia.Paint:
        key = (hexval, alpha)
        if key not in self._paints:
            r, g, b = palette.rgb(hexval)
            p = skia.Paint(AntiAlias=True, Color=skia.Color(r, g, b, round(alpha * 255)))
            self._paints[key] = p
        return self._paints[key]

    def cell_origin(self, x: int, y: int) -> tuple[float, float]:
        return PAD + x * CELL_W, PAD + y * CELL_H

    @staticmethod
    def colors(char: pyte.screens.Char) -> tuple[str, str]:
        fg = palette.resolve(char.fg, palette.FG)
        bg = palette.resolve(char.bg, palette.BG)
        if char.reverse:
            fg, bg = bg, fg
        return fg, bg

    def draw_glyph(self, canvas: skia.Canvas, char: pyte.screens.Char, x: int, y: int,
                   fg: str, alpha: float = 1.0) -> None:
        data = char.data
        if not data or data == " ":
            return
        ox, oy = self.cell_origin(x, y)
        paint = self.paint(fg, alpha)
        glyph = data[0]
        if len(data) == 1 and self.proc.claims(glyph):
            self.proc.draw(canvas, glyph, ox, oy, paint)
            return
        span = 2 if wcwidth(glyph) == 2 else 1
        font, primary = self.fonts.pick(glyph, char.bold, char.italics)
        if primary:
            canvas.drawString(data, ox, oy + self.fonts.baseline, font, paint)
        else:
            self._draw_fallback(canvas, data, font, ox, oy, span * CELL_W, paint)
        if char.underscore:
            canvas.drawRect(skia.Rect.MakeXYWH(ox, oy + CELL_H - 8, CELL_W * span, 3), paint)
        if char.strikethrough:
            canvas.drawRect(skia.Rect.MakeXYWH(ox, oy + CELL_H / 2, CELL_W * span, 3), paint)

    def _draw_fallback(self, canvas, data, font, ox, oy, span_w, paint) -> None:
        bounds = skia.Rect()
        advance = font.measureText(data, bounds=bounds)
        scale = min(1.0, span_w * 0.96 / advance) if advance else 1.0
        # Symbol fonts draw some marks (e.g. U+27F3) far smaller than the terminal font's.
        target = font.getSize() * 0.62
        if 0 < bounds.height() < target * 0.85 and bounds.width() > 0:
            scale = min(target / bounds.height(), span_w * 0.9 / bounds.width())
        if font is self.fonts.emoji:
            scale = min(span_w * 0.92 / advance, CELL_H * 0.8 / font.getSize()) if advance else 1.0
        canvas.save()
        cx = ox + span_w / 2
        baseline = oy + self.fonts.baseline
        canvas.translate(cx, baseline)
        canvas.scale(scale, scale)
        canvas.drawString(data, -advance / 2, 0 if font is not self.fonts.emoji else -2, font, paint)
        canvas.restore()

    def render_base(self, buffer: list[list[pyte.screens.Char]]) -> None:
        canvas = self.surface.getCanvas()
        canvas.clear(skia.Color(*palette.rgb(palette.BG)))
        for y, row in enumerate(buffer):
            x = 0
            while x < len(row):
                _, bg = self.colors(row[x])
                if bg == palette.BG:
                    x += 1
                    continue
                start = x
                while x < len(row) and self.colors(row[x])[1] == bg:
                    x += 1
                ox, oy = self.cell_origin(start, y)
                canvas.drawRect(skia.Rect.MakeXYWH(ox, oy, (x - start) * CELL_W, CELL_H),
                                self.paint(bg))
        for y, row in enumerate(buffer):
            for x, char in enumerate(row):
                fg, _ = self.colors(char)
                self.draw_glyph(canvas, char, x, y, fg)
        self.base = self.surface.makeImageSnapshot()

    def frame(self, buffer, cursor: tuple[int, int] | None, cursor_alpha: float) -> bytes:
        canvas = self.surface.getCanvas()
        canvas.drawImage(self.base, 0, 0)
        if cursor is not None and cursor_alpha > 0.01:
            x, y = cursor
            if 0 <= x < self.geo.cols and 0 <= y < self.geo.rows:
                char = buffer[y][x]
                fg, bg = self.colors(char)
                ox, oy = self.cell_origin(x, y)
                canvas.drawRect(skia.Rect.MakeXYWH(ox, oy, CELL_W, CELL_H),
                                self.paint(palette.FG, cursor_alpha * 0.92))
                self.draw_glyph(canvas, char, x, y, bg, cursor_alpha)
        return self.surface.makeImageSnapshot().tobytes()

    def still(self, path: Path) -> None:
        self.surface.makeImageSnapshot().save(str(path), skia.kPNG)


def cursor_alpha(since_input: float) -> float:
    """Solid while typing, then a soft blink: 0.55 s on, eased 0.12 s fades."""
    if since_input < 0.6:
        return 1.0
    phase = (since_input - 0.6) % 1.1
    def ease(u: float) -> float:
        return u * u * (3 - 2 * u)
    if phase < 0.55:
        return 1.0
    if phase < 0.67:
        return 1.0 - ease((phase - 0.55) / 0.12)
    if phase < 0.98:
        return 0.0
    return ease((phase - 0.98) / 0.12)


def encoder(path: Path, width: int, height: int) -> subprocess.Popen:
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{width}x{height}", "-r", str(FPS),
        "-i", "-",
        "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
        "-c:v", "libx264", "-preset", "slow", "-crf", "10", "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-r", str(FPS), "-fps_mode", "cfr", "-movflags", "+faststart", str(path),
    ]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


@dataclass
class Recording:
    """Output bytes with times (s) relative to video start; negative = pre-roll."""

    cols: int
    rows: int
    events: list[tuple[float, bytes]]
    duration: float
    inputs: list[float]  # times of keystrokes, for the cursor blink phase
    show_cursor: bool = True


def render_recording(rec: Recording, out_mp4: Path, still_png: Path, still_t: float) -> dict:
    geo = Geometry(rec.cols, rec.rows)
    renderer = TerminalRenderer(geo)
    screen = VtScreen(rec.cols, rec.rows)
    stream = VtStream(screen)
    events = sorted(rec.events, key=lambda e: e[0])
    proc = encoder(out_mp4, *geo.size)
    frames = round(rec.duration * FPS)
    still_frame = min(frames - 1, round(still_t * FPS))
    idx = 0
    last_bytes = None
    last_key = None
    buffer = None
    for n in range(frames):
        t = n / FPS
        changed = buffer is None
        while idx < len(events) and events[idx][0] <= t:
            stream.feed(events[idx][1])
            idx += 1
            changed = True
        if changed:
            buffer = [[screen.buffer[y][x] for x in range(rec.cols)] for y in range(rec.rows)]
            renderer.render_base(buffer)
        visible = rec.show_cursor and not screen.cursor.hidden
        cursor = (screen.cursor.x, screen.cursor.y) if visible else None
        past = [i for i in rec.inputs if i <= t]
        alpha = cursor_alpha(t - past[-1] if past else t) if visible else 0.0
        key = (changed, cursor, round(alpha, 3))
        if last_bytes is None or changed or key != last_key:
            last_bytes = renderer.frame(buffer, cursor, alpha)
        last_key = (False, cursor, round(alpha, 3))
        proc.stdin.write(last_bytes)
        if n == still_frame:
            renderer.still(still_png)
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {out_mp4}")
    width, height = geo.size
    return {
        "size": [width, height],
        "fps": FPS,
        "duration": round(frames / FPS, 3),
        "grid": f"{rec.cols}x{rec.rows}",
        "cell_px": [CELL_W, CELL_H],
        "padding_px": PAD,
    }
