"""Streamed video decode through ffmpeg pipes, with a prefetch thread per reader.

Opaque sources come out as NV12 (converted to linear RGB on the GPU with the stream's own
matrix); sources with alpha come out as RGBA. Frames are addressed by source time; the
reader moves forward through the pipe and restarts with an input seek when asked to go
back.
"""

import json
import queue
import subprocess
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .hw import cuda_decode, hwaccel

ALPHA_FORMATS = ("yuva", "rgba", "bgra", "argb", "abgr", "gbrap", "ya")


@dataclass(frozen=True)
class Probe:
    width: int
    height: int
    fps: float
    duration: float
    pix_fmt: str
    matrix: str  # "bt709" or "bt601"
    full_range: bool

    @property
    def alpha(self) -> bool:
        return self.pix_fmt.startswith(ALPHA_FORMATS)


@lru_cache(maxsize=None)
def probe(path: str) -> Probe:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-show_format",
         "-of", "json", path],
        check=True, capture_output=True, text=True,
    ).stdout
    info = json.loads(out)
    st = info["streams"][0]
    num, den = st.get("avg_frame_rate", "60/1").split("/")
    fps = float(num) / float(den) if float(den) else 60.0
    dur = float(st.get("duration") or info["format"].get("duration") or 0)
    space = st.get("color_space", "")
    # untagged streams come from ffmpeg's rgb->yuv default, which is BT.601 (motion/lib/encode.py)
    matrix = "bt709" if space == "bt709" else "bt601"
    return Probe(int(st["width"]), int(st["height"]), fps, dur, st.get("pix_fmt", ""),
                 matrix, st.get("color_range") == "pc")


class VideoReader:
    """Sequential frame source. `frame(t)` returns the raw frame bytes for source time t."""

    def __init__(self, path: str | Path, size: tuple[int, int] | None = None, hw: bool = True):
        self.path = str(path)
        self.info = probe(self.path)
        self.size = size or (self.info.width, self.info.height)
        self.alpha = self.info.alpha
        self.hw = hw and bool(hwaccel()) and not self.alpha and self.info.pix_fmt in ("yuv420p", "nv12", "yuvj420p")
        w, h = self.size
        self.frame_bytes = w * h * 4 if self.alpha else w * h * 3 // 2
        self._proc = None
        self._thread = None
        self._q: queue.Queue = queue.Queue(maxsize=6)
        self._index = -1  # index (relative to the stream origin) of self._last
        self._origin = 0  # absolute source frame index the pipe started at
        self._last = None
        self.frame_count = max(1, round(self.info.duration * self.info.fps))

    # -- pipe management -------------------------------------------------------------------
    def _cmd(self, start_frame: int) -> list[str]:
        w, h = self.size
        scaled = (w, h) != (self.info.width, self.info.height)
        cmd = ["ffmpeg", "-v", "error", "-nostdin"]
        cuda_scale = self.hw and scaled and cuda_decode()  # VideoToolbox frames are scaled on the CPU
        if self.hw:
            cmd += hwaccel()
            if cuda_scale:
                cmd += ["-hwaccel_output_format", "cuda"]
        if start_frame:
            cmd += ["-ss", f"{start_frame / self.info.fps:.6f}"]
        cmd += ["-i", self.path, "-an", "-sn"]
        if scaled:
            if cuda_scale:
                cmd += ["-vf", f"scale_cuda={w}:{h}:format=nv12:interp_algo=lanczos,hwdownload,format=nv12"]
            else:
                cmd += ["-vf", f"scale={w}:{h}:flags=area"]
        cmd += ["-fps_mode", "passthrough", "-f", "rawvideo",
                "-pix_fmt", "rgba" if self.alpha else "nv12", "-"]
        return cmd

    def _pump(self, proc, q, stop):
        n = self.frame_bytes
        try:
            while not stop.is_set():
                buf = proc.stdout.read(n)
                if not buf or len(buf) < n:
                    break
                self._put(q, buf, stop)
        except (ValueError, OSError):
            pass  # pipe closed by close()
        self._put(q, None, stop)

    @staticmethod
    def _put(q, item, stop):
        while not stop.is_set():
            try:
                q.put(item, timeout=0.1)
                return
            except queue.Full:
                continue

    def _open(self, start_frame: int) -> None:
        self.close()
        self._q = queue.Queue(maxsize=6)
        self._stop = threading.Event()
        self._proc = subprocess.Popen(self._cmd(start_frame), stdout=subprocess.PIPE,
                                      bufsize=self.frame_bytes * 2)
        self._thread = threading.Thread(target=self._pump, args=(self._proc, self._q, self._stop), daemon=True)
        self._thread.start()
        self._origin = start_frame
        self._index = -1
        self._eof = False

    def close(self) -> None:
        if self._proc:
            self._stop.set()
            self._proc.kill()
            self._thread.join(timeout=2)
            self._proc.stdout.close()
            self._proc.wait()
            self._proc = None

    # -- access ----------------------------------------------------------------------------
    def frame_index(self, t: float) -> int:
        n = int(t * self.info.fps + 1e-4)
        return min(max(n, 0), self.frame_count - 1)

    def frame(self, t: float) -> bytes:
        want = self.frame_index(t)
        rel = want - self._origin
        if self._proc is None or rel < self._index or rel - self._index > 90:
            self._open(want)
            rel = 0
        while self._index < rel and not self._eof:
            buf = self._q.get()
            if buf is None:
                self._eof = True
                break
            self._last = buf
            self._index += 1
        if self._last is None:
            raise RuntimeError(f"no frames decoded from {self.path} at t={t:.3f}")
        return self._last
