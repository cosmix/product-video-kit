"""What this machine offers the edit: the GL context, a fast H.264 encoder, decode acceleration.

Linux renders through headless EGL: an NVIDIA, AMD or Intel driver, or Mesa's llvmpipe on the
CPU when there is no GPU. macOS has no EGL: moderngl opens a CGL context there (OpenGL 4.1
core, which is what the shaders target). Hardware encode (NVENC, VideoToolbox) and CUDA decode
are used only when a probe shows they work; otherwise ffmpeg encodes with libx264 and decodes
and scales on the CPU. Each probe runs once per process.
"""

import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

MAC = sys.platform == "darwin"
GL_CONTEXT = {"require": 410} if MAC else {"backend": "egl", "require": 410}
_TEST_SRC = ["-f", "lavfi", "-i", "testsrc2=s=256x144:r=30:d=0.2"]


def _ffmpeg_ok(*args: str) -> bool:
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", *args]
    try:
        return subprocess.run(cmd, capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@lru_cache(maxsize=None)
def _encoder_works(name: str, args: tuple[str, ...]) -> bool:
    """True when ffmpeg lists the encoder and a short test encode through it succeeds (a build
    can list h264_nvenc on a machine with no NVIDIA driver). `args` are the encoder arguments the
    real encode uses, so a driver that rejects them fails the probe."""
    try:
        listed = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True,
                                timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return name in listed and _ffmpeg_ok(*_TEST_SRC, *args, "-f", "null", "-")


@lru_cache(maxsize=1)
def cuda_decode() -> bool:
    """True when ffmpeg decodes and scales H.264 through CUDA here (Linux with an NVIDIA driver)."""
    if MAC:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        clip = str(Path(tmp) / "probe.mp4")
        if not _ffmpeg_ok(*_TEST_SRC, "-c:v", "libx264", "-pix_fmt", "yuv420p", clip):
            return False
        return _ffmpeg_ok("-hwaccel", "cuda", "-hwaccel_output_format", "cuda", "-i", clip,
                          "-vf", "scale_cuda=128:72:format=nv12,hwdownload,format=nv12", "-f", "null", "-")


def hwaccel() -> list[str]:
    """ffmpeg input arguments for hardware decode, or [] to decode on the CPU."""
    if MAC:
        return ["-hwaccel", "videotoolbox"]
    return ["-hwaccel", "cuda"] if cuda_decode() else []


def fast_h264(nvenc_preset: str, cq: int) -> list[str]:
    """Encoder arguments for previews and placeholders: NVENC or VideoToolbox when they work here,
    else libx264 at a fast preset."""
    vt = ["-c:v", "h264_videotoolbox", "-b:v", "20M"]
    nv = ["-c:v", "h264_nvenc", "-preset", nvenc_preset, "-cq", str(cq)]
    if MAC and _encoder_works("h264_videotoolbox", tuple(vt)):
        return vt
    if not MAC and _encoder_works("h264_nvenc", tuple(nv)):
        return nv
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(cq)]
