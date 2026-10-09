"""OpenGL plumbing (EGL on Linux, CGL on macOS): programs, render targets, and source textures.

Convention: every texture and render target stores the image top at row 0, so a buffer
read back with `read()` is already in top-to-bottom order for ffmpeg.
"""

from pathlib import Path

import moderngl
import numpy as np

from .hw import GL_CONTEXT

SHADERS = Path(__file__).parent / "shaders"

# Y'CbCr -> R'G'B' (column-major for GLSL mat3)
_MATRICES = {
    "bt709": np.array([[1, 1, 1], [0, -0.187324, 1.8556], [1.5748, -0.468124, 0]], dtype="f4"),
    "bt601": np.array([[1, 1, 1], [0, -0.344136, 1.772], [1.402, -0.714136, 0]], dtype="f4"),
}


class GPU:
    def __init__(self):
        self.ctx = moderngl.create_standalone_context(**GL_CONTEXT)
        self.ctx.enable_only(moderngl.BLEND)
        self.ctx.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA
        self.vao_empty = {}
        self.programs = {}
        common = (SHADERS / "common.glsl").read_text()
        for frag in SHADERS.glob("*.frag"):
            vert = "plane.vert" if frag.stem in ("plane", "shadow") else "fullscreen.vert"
            src = "#version 410\n" + common + frag.read_text()
            prog = self.ctx.program(vertex_shader=(SHADERS / vert).read_text(), fragment_shader=src)
            self.programs[frag.stem] = prog
            self.vao_empty[frag.stem] = self.ctx.vertex_array(prog, [])
        self._pool: dict[tuple, list] = {}

    # -- programs --------------------------------------------------------------------------
    def set(self, name: str, **uniforms) -> moderngl.Program:
        prog = self.programs[name]
        for k, v in uniforms.items():
            key = "u_" + k
            if key not in prog:
                continue
            u = prog[key]
            if isinstance(v, np.ndarray):
                u.write(v.astype("f4").tobytes())
            else:
                u.value = v
        return prog

    def draw_fullscreen(self, name: str, **uniforms) -> None:
        self.set(name, **uniforms)
        self.vao_empty[name].render(moderngl.TRIANGLES, vertices=3)

    def draw_quad(self, name: str, **uniforms) -> None:
        self.set(name, **uniforms)
        self.vao_empty[name].render(moderngl.TRIANGLE_STRIP, vertices=4)

    # -- render targets --------------------------------------------------------------------
    def target(self, size: tuple[int, int], dtype: str = "f2", mips: bool = False) -> "Target":
        key = (size, dtype, mips)
        free = self._pool.setdefault(key, [])
        return free.pop() if free else Target(self.ctx, size, dtype, mips, self)

    def release(self, t: "Target") -> None:
        self._pool.setdefault((t.size, t.dtype, t.mips), []).append(t)


class Target:
    def __init__(self, ctx, size, dtype, mips, gpu):
        self.size, self.dtype, self.mips = size, dtype, mips
        self.tex = ctx.texture(size, 4, dtype=dtype)
        self.tex.repeat_x = self.tex.repeat_y = False
        if mips:
            self.tex.build_mipmaps()
            self.tex.filter = moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR
        else:
            self.tex.filter = moderngl.LINEAR, moderngl.LINEAR
        self.fbo = ctx.framebuffer(color_attachments=[self.tex])
        self.gpu = gpu

    def use(self, clear: tuple | None = (0, 0, 0, 0)) -> "Target":
        self.fbo.use()
        if clear is not None:
            self.fbo.clear(*clear)
        return self

    def build_mips(self) -> None:
        if self.mips:
            self.tex.build_mipmaps()

    def release(self) -> None:
        self.gpu.release(self)


class SourceTexture:
    """A decoded frame converted to linear premultiplied RGBA16F with a full mip chain."""

    def __init__(self, gpu: GPU, size: tuple[int, int], alpha: bool, matrix: str = "bt709",
                 full_range: bool = False):
        self.gpu, self.size, self.alpha = gpu, size, alpha
        ctx = gpu.ctx
        w, h = size
        if alpha:
            self.y = ctx.texture(size, 4, dtype="f1")
        else:
            self.y = ctx.texture(size, 1, dtype="f1")
            self.uv = ctx.texture((w // 2, h // 2), 2, dtype="f1")
            self.uv.filter = moderngl.LINEAR, moderngl.LINEAR
        self.y.filter = moderngl.NEAREST, moderngl.NEAREST
        self.tex = ctx.texture(size, 4, dtype="f2")
        self.tex.repeat_x = self.tex.repeat_y = False
        self.tex.build_mipmaps()
        self.tex.filter = moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR
        self.tex.anisotropy = 16.0
        self.fbo = ctx.framebuffer(color_attachments=[self.tex])
        self.matrix = _MATRICES[matrix]
        if full_range:
            self.offset, self.scale = (0.0, 0.5, 0.5), (1.0, 1.0, 1.0)
        else:
            self.offset = (16 / 255, 128 / 255, 128 / 255)
            self.scale = (255 / 219, 255 / 224, 255 / 224)
        self._last = None

    def update(self, frame: bytes) -> None:
        if frame is self._last:
            return
        self._last = frame
        w, h = self.size
        if self.alpha:
            self.y.write(frame)
        else:
            self.y.write(memoryview(frame)[: w * h])
            self.uv.write(memoryview(frame)[w * h:])
        self._convert()

    def update_rgba(self, rgba: np.ndarray) -> None:
        """Straight-alpha sRGB RGBA8 image (stills, text, generated art)."""
        self.y.write(np.ascontiguousarray(rgba, dtype=np.uint8).tobytes())
        self._convert()

    def _convert(self) -> None:
        g = self.gpu
        self.fbo.use()
        g.ctx.disable(moderngl.BLEND)
        self.y.use(0)
        if not self.alpha:
            self.uv.use(1)
        g.draw_fullscreen("convert", mode=1 if self.alpha else 0, y=0, uv=1, matrix=self.matrix,
                          offset=self.offset, scale=self.scale)
        g.ctx.enable(moderngl.BLEND)
        self.tex.build_mipmaps()

    def release(self) -> None:
        for obj in (self.fbo, self.tex, self.y, getattr(self, "uv", None)):
            if obj is not None:
                obj.release()


def image_texture(gpu: GPU, rgba: np.ndarray) -> SourceTexture:
    h, w = rgba.shape[:2]
    st = SourceTexture(gpu, (w, h), alpha=True)
    st.update_rgba(rgba)
    return st
