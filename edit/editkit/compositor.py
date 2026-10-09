"""Frame compositor: background, scene groups with transitions, per-layer depth of field,
shutter-sampled motion blur, bloom and grain.
"""

import math
from dataclasses import dataclass, field

import moderngl
import numpy as np

from . import art, design
from .assets import resolve
from .decode import VideoReader
from .ease import value
from .gpu import GPU, SourceTexture, image_texture
from .scene import DESIGN, FLIP, Camera, Plane, Timeline, group_state

SHADOW_LAYERS = np.array([[3, 2.5, 0.28, 0], [16, 22, 0.30, 0], [52, 90, 0.42, 8]], dtype="f4")


def _lin(rgb):
    return tuple(((c / 255 + 0.055) / 1.055) ** 2.4 if c / 255 > 0.04045 else c / 255 / 12.92 for c in rgb)


@dataclass
class Quality:
    res: tuple = (1920, 1080)
    fps: int = 60
    grain: float = field(default_factory=design.grain)
    dof: bool = True
    motion_blur: bool = True
    bloom: float = 0.12
    decode_scale: float = 1.0


PREVIEW = Quality(res=(960, 540), fps=30, grain=0.0, dof=False, motion_blur=False, bloom=0.16, decode_scale=0.5)


class LayerSource:
    """Decoder + GPU texture for one Plane."""

    def __init__(self, gpu: GPU, plane: Plane, q: Quality):
        self.asset = resolve(plane.source)
        if self.asset.still:
            from PIL import Image

            img = np.asarray(Image.open(self.asset.path).convert("RGBA"))
            self.reader = None
            self.tex = image_texture(gpu, img)
            h, w = img.shape[:2]
            self.native = (w, h)
            return
        info = self.asset.info
        self.native = (info.width, info.height)
        size = (info.width, info.height)
        if q.decode_scale < 1 and info.width >= 1920:
            size = (int(info.width * q.decode_scale) // 2 * 2, int(info.height * q.decode_scale) // 2 * 2)
        self.reader = VideoReader(self.asset.path, size=size)
        self.tex = SourceTexture(gpu, size, alpha=info.alpha, matrix=info.matrix, full_range=info.full_range)

    def content_size(self) -> tuple:
        w, h = self.native
        return (w / 2, h / 2) if w >= 3000 else (float(w), float(h))

    def update(self, t_src: float) -> None:
        if self.reader is not None:
            self.tex.update(self.reader.frame(t_src))

    def close(self) -> None:
        if self.reader is not None:
            self.reader.close()
        self.tex.release()


class Compositor:
    def __init__(self, timeline: Timeline, q: Quality):
        self.tl, self.q = timeline, q
        self.gpu = GPU()
        self.sources: dict[int, LayerSource] = {}
        self.bars: dict[tuple, SourceTexture] = {}
        cur, self.cursor_css, self.cursor_hot = art.cursor_sprite()
        self.cursor_tex = image_texture(self.gpu, cur)
        self.white = image_texture(self.gpu, np.full((4, 4, 4), 255, np.uint8))
        self.clear_tex = image_texture(self.gpu, np.zeros((4, 4, 4), np.uint8))
        res = q.res
        self.frame = self.gpu.target(res)
        self.accum = self.gpu.target(res, "f4")
        self.group = self.gpu.target(res)
        self.scratch = self.gpu.target(res, mips=True)
        self.out = self.gpu.ctx.texture(res, 4, dtype="f1")
        self.out_fbo = self.gpu.ctx.framebuffer(color_attachments=[self.out])
        self.bloom_levels = []
        w, h = res[0] // 2, res[1] // 2
        for _ in range(6):
            self.bloom_levels.append(self.gpu.target((max(w, 1), max(h, 1))))
            w, h = w // 2, h // 2

    # -- resources -------------------------------------------------------------------------
    def source(self, plane: Plane) -> LayerSource:
        k = id(plane)
        if k not in self.sources:
            self.sources[k] = LayerSource(self.gpu, plane, self.q)
        return self.sources[k]

    def retire(self, t: float) -> None:
        """Close decoders for layers that have ended."""
        live = {id(layer) for seg in self.tl.segments for layer in seg.layers
                if isinstance(layer, Plane) and layer.end > t - 0.05}
        for k in [k for k in self.sources if k not in live]:
            self.sources.pop(k).close()

    def bar(self, kind: str, title: str, width: float) -> SourceTexture:
        key = (kind, title, int(width))
        if key not in self.bars:
            self.bars[key] = image_texture(self.gpu, art.title_bar(kind, title, int(width), int(Plane.titlebar_h)))
        return self.bars[key]

    # -- frame -----------------------------------------------------------------------------
    def render(self, t: float) -> bytes:
        dt = 1.0 / self.q.fps
        n = self.shutter_samples(t, dt) if self.q.motion_blur else 1
        if n == 1:
            self.compose(t, self.frame)
            src = self.frame
        else:
            self.accum.use()
            for i in range(n):
                ts = t + ((i + 0.5) / n - 0.5) * dt * 0.5  # 180 degree shutter
                self.compose(ts, self.frame)
                self.accum.use(clear=None)
                self.gpu.ctx.blend_func = moderngl.ONE, moderngl.ONE
                self.frame.tex.use(0)
                self.gpu.draw_fullscreen("copy", src=0, weight=1.0 / n)
                self.gpu.ctx.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA
            src = self.accum
        self.bloom(src)
        return self.finish(src, t)

    def compose(self, t: float, target) -> None:
        g = self.gpu
        target.use(clear=(0, 0, 0, 1))
        g.ctx.disable(moderngl.BLEND)
        g.draw_fullscreen("background", color=_lin(art.BACKGROUND), level=float(value(self.tl.background_level, t)))
        g.ctx.enable(moderngl.BLEND)
        for seg, nxt in self.tl.active_segments(t):
            gs = group_state(seg, nxt, t)
            if gs.opacity <= 0.001:
                continue
            self.group.use()
            for layer in self.draw_order(seg, t):
                self.draw_plane(layer, seg.camera, t, self.group)
            target.use(clear=None)
            self.group.tex.use(0)
            g.draw_fullscreen("group", src=0, res=DESIGN, opacity=gs.opacity, offset=gs.offset, zoom=gs.zoom)

    # -- layers ----------------------------------------------------------------------------
    def draw_order(self, seg, t: float) -> list:
        """Active planes in list order, except that world-space planes are painted far to
        near among the slots they occupy (screen planes keep their place)."""
        layers = [p for p in seg.layers if isinstance(p, Plane) and p.active(t)]
        world = [i for i, p in enumerate(layers) if p.space == "world"]
        if len(world) < 2:
            return layers
        eye = seg.camera.state(t)[0]

        def depth(p):
            pos = value(p.pos, t)
            z = pos[2] if len(pos) > 2 else 0.0
            return -float(np.linalg.norm(np.array([pos[0], pos[1], z]) - eye))

        ordered = sorted((layers[i] for i in world), key=depth)
        for slot, p in zip(world, ordered):
            layers[slot] = p
        return layers

    def draw_plane(self, p: Plane, cam: Camera, t: float, dest) -> None:
        g = self.gpu
        alpha = p.alpha(t)
        if alpha <= 0.002:
            return
        src = self.source(p)
        src.update(p.source_time(t))
        content = p.size or src.content_size()
        W, H = p.window_size(content)
        mvp = p.mvp(t, content, cam)
        mvp_b = mvp.T.astype("f4").copy()
        tb = Plane.titlebar_h if p.chrome else 0.0
        # created before binding the scratch target: making a texture binds its own FBO
        bar = self.bar(p.chrome, p.title, W) if p.chrome else self.clear_tex
        self.scratch.use()
        if p.shadow:
            pad = 300.0
            g.draw_quad("shadow", mvp=mvp_b, origin=(-pad, -pad), extent=(W + 2 * pad, H + 2 * pad),
                        size=(W, H), radius=p.radius, opacity=alpha * 0.9,
                        layers=SHADOW_LAYERS,
                        color=(0.003, 0.002, 0.005))
        src.tex.tex.use(0)
        bar.tex.use(1)
        self.cursor_tex.tex.use(2)
        view = value(p.view, t)
        uni = dict(mvp=mvp_b, origin=(0.0, 0.0), extent=(W, H), size=(W, H), radius=p.radius, titlebar=tb,
                   content=0, view=view, lod_bias=-0.25, bar=1, bar_color=_lin(art.BAR),
                   border_color=_lin(art.HAIRLINE), border_alpha=1.0, opacity=alpha,
                   dim=float(value(p.dim, t)), sat=float(value(p.saturation, t)), cursor=2, cursor_on=0)
        if p.cursor is not None:
            uni.update(self.cursor_uniforms(p, t))
        g.draw_quad("plane", **uni)
        self.resolve_layer(p, cam, t, dest, content)

    def cursor_uniforms(self, p: Plane, t: float) -> dict:
        c = p.cursor
        ts = p.source_time(t)
        vw, vh = c.viewport
        x, y = c.pos(ts)
        rip = np.zeros((4, 4), dtype="f4")
        for i, (ct, age) in enumerate(c.ripples(ts)):
            cx, cy = c.pos(ct)
            rip[i] = (cx / vw, cy / vh, age, 1.0)
        sw, sh = self.cursor_css
        return dict(cursor_on=1, cursor_pos=(x / vw, y / vh), cursor_size=(sw * c.scale / vw, sh * c.scale / vh),
                    cursor_hot=self.cursor_hot, ripples=rip, capture_px=(float(vw), float(vh)))

    def resolve_layer(self, p: Plane, cam: Camera, t: float, dest, content) -> None:
        """Scratch -> dest through the depth-of-field gather."""
        g = self.gpu
        blur = float(value(p.blur, t))
        uni = dict(src=0, res=DESIGN, plane=0, blur=blur, aperture=0.0, focus=1.0, max_radius=64.0)
        if self.q.dof and p.space == "world":
            proj, view, eye, fwd, focus, aperture = cam.matrices(t)
            if aperture > 0:
                m = FLIP @ p.model(t, content)
                W, H = p.window_size(content)
                p0 = (m @ np.array([W / 2, H / 2, 0, 1]))[:3]
                n = m[:3, :3] @ np.array([0, 0, 1.0])
                n /= np.linalg.norm(n)
                inv = np.linalg.inv(proj @ view)
                uni.update(plane=1, inv_vp=inv.T.astype("f4").copy(), eye=tuple(eye), fwd=tuple(fwd),
                           p0=tuple(p0), n=tuple(n), focus=focus, aperture=aperture)
        if blur > 0.3 or uni["plane"] == 1:
            self.scratch.build_mips()
        dest.use(clear=None)
        self.scratch.tex.use(0)
        g.draw_fullscreen("dof", **uni)

    # -- motion blur -----------------------------------------------------------------------
    def shutter_samples(self, t: float, dt: float) -> int:
        a, b = self.corners(t - dt * 0.25), self.corners(t + dt * 0.25)
        if not a or len(a) != len(b):
            return 1
        disp = max(float(np.max(np.linalg.norm(x - y, axis=1))) for x, y in zip(a, b))
        return int(min(max(math.ceil(disp / 1.1), 1), 64))

    def corners(self, t: float) -> list:
        out = []
        for seg, nxt in self.tl.active_segments(t):
            gs = group_state(seg, nxt, t)
            for p in seg.layers:
                if not (isinstance(p, Plane) and p.active(t)):
                    continue
                src = self.sources.get(id(p))
                content = p.size or (src.content_size() if src else (1920.0, 1080.0))
                W, H = p.window_size(content)
                pts = np.array([[0, 0, 0, 1], [W, 0, 0, 1], [0, H, 0, 1], [W, H, 0, 1]], dtype=float).T
                c = p.mvp(t, content, seg.camera) @ pts
                ndc = (c[:2] / c[3]).T
                px = (ndc * [0.5, -0.5] + 0.5) * DESIGN
                px = (px - np.array(DESIGN) / 2) * gs.zoom + np.array(DESIGN) / 2 + gs.offset
                out.append(px)
        return out

    # -- post ------------------------------------------------------------------------------
    def bloom(self, src) -> None:
        g = self.gpu
        g.ctx.disable(moderngl.BLEND)
        prev = src
        for i, lvl in enumerate(self.bloom_levels):
            lvl.use(clear=None)
            prev.tex.use(0)
            g.draw_fullscreen("bloom", src=0, texel=(1 / prev.size[0], 1 / prev.size[1]), mode=0 if i == 0 else 1,
                              threshold=0.8, knee=0.3)
            prev = lvl
        g.ctx.enable(moderngl.BLEND)
        g.ctx.blend_func = moderngl.ONE, moderngl.ONE
        for i in range(len(self.bloom_levels) - 1, 0, -1):
            lo, hi = self.bloom_levels[i], self.bloom_levels[i - 1]
            hi.use(clear=None)
            lo.tex.use(0)
            g.draw_fullscreen("bloom", src=0, texel=(1 / lo.size[0], 1 / lo.size[1]), mode=2)
        g.ctx.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA

    def finish(self, src, t: float) -> bytes:
        g = self.gpu
        self.out_fbo.use()
        g.ctx.disable(moderngl.BLEND)
        src.tex.use(0)
        self.bloom_levels[0].tex.use(1)
        g.draw_fullscreen("final", frame=0, bloom=1, res=self.q.res, bloom_amt=self.q.bloom,
                          grain=self.q.grain, seed=float(round(t * self.q.fps) % 997),
                          fade=float(value(self.tl.fade, t)))
        g.ctx.enable(moderngl.BLEND)
        return self.out_fbo.read(components=3)

    def close(self) -> None:
        for s in self.sources.values():
            s.close()
        self.sources.clear()
