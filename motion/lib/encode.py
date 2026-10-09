"""ffmpeg writers and the contact sheet."""

import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import design
from .gfx import BG, H, W, rgb


class Writer:
    def __init__(self, path, fps, alpha):
        self.alpha = alpha
        common = [
            "ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
            "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
        ]
        if alpha:
            codec = ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-vendor", "apl0"]
        else:
            codec = ["-c:v", "libx264", "-crf", "10", "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        self.proc = subprocess.Popen(common + codec + [path], stdin=subprocess.PIPE)

    def write(self, rgba):
        self.proc.stdin.write(np.ascontiguousarray(rgba).tobytes())

    def close(self):
        self.proc.stdin.close()
        rc = self.proc.wait()
        if rc != 0:
            raise RuntimeError(f"ffmpeg exited {rc}")


def contact_sheet(frames, times, path, cols=3):
    """frames: list of RGBA arrays. Composites over the background colour for viewing, labels t."""
    tw, th = W // 3, H // 3
    rows = (len(frames) + cols - 1) // cols
    ground = tuple(round(255 * c) for c in rgb(BG))
    sheet = Image.new("RGB", (cols * tw, rows * th), ground)
    fnt = ImageFont.truetype(design.font(500), 18)
    for i, (fr, t) in enumerate(zip(frames, times)):
        im = Image.fromarray(fr, "RGBA")
        bg = Image.new("RGBA", im.size, ground + (255,))
        im = Image.alpha_composite(bg, im).convert("RGB").resize((tw, th), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 70, 24], fill=(0, 0, 0))
        d.text((6, 3), f"{t:5.2f}s", font=fnt, fill=(255, 255, 255))
        sheet.paste(im, ((i % cols) * tw, (i // cols) * th))
    sheet.save(path)


def save_png(rgba, path):
    Image.fromarray(rgba, "RGBA").save(path)
