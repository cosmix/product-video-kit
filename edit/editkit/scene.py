"""Scene description: cameras, layers, segments, transitions, and the matrices they imply.

World space is "design px": x right, y down, z into the screen, with the default camera
framing the rectangle (0,0)-(1920,1080) at z = 0 exactly. GL world (y up, z toward the
viewer) is world with y and z negated.
"""

import math
from dataclasses import dataclass, field

import numpy as np

from .ease import Track, ramp, value

DESIGN = (1920, 1080)
FLIP = np.diag([1.0, -1.0, -1.0, 1.0])


def _translate(x, y, z=0.0):
    m = np.eye(4)
    m[:3, 3] = (x, y, z)
    return m


def _scale(sx, sy, sz=1.0):
    return np.diag([sx, sy, sz, 1.0])


def _rot(rx, ry, rz):
    """Rotation in world space (degrees): about x (tilt), y (swing), z (roll)."""
    a, b, c = (math.radians(v) for v in (rx, ry, rz))
    ca, sa, cb, sb, cc, sc = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(c), math.sin(c)
    Rx = np.array([[1, 0, 0, 0], [0, ca, -sa, 0], [0, sa, ca, 0], [0, 0, 0, 1]])
    Ry = np.array([[cb, 0, sb, 0], [0, 1, 0, 0], [-sb, 0, cb, 0], [0, 0, 0, 1]])
    Rz = np.array([[cc, -sc, 0, 0], [sc, cc, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
    return Ry @ Rx @ Rz


def _look_at(eye, target, up=(0.0, 1.0, 0.0)):
    eye, target, up = (np.asarray(v, dtype=float) for v in (eye, target, up))
    f = target - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, up)
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.eye(4)
    m[0, :3], m[1, :3], m[2, :3] = s, u, -f
    m[:3, 3] = -m[:3, :3] @ eye
    return m


def _perspective(fov_deg, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fov_deg) / 2)
    m = np.zeros((4, 4))
    m[0, 0], m[1, 1] = f / aspect, f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2 * far * near / (near - far)
    m[3, 2] = -1.0
    return m


def ortho_screen():
    """Design px (y down) -> GL clip space (y up); the vertex shader flips y back."""
    w, h = DESIGN
    m = np.eye(4)
    m[0, 0], m[0, 3] = 2 / w, -1
    m[1, 1], m[1, 3] = -2 / h, 1
    m[2, 2] = -1e-4
    return m


def home_distance(fov: float) -> float:
    return (DESIGN[1] / 2) / math.tan(math.radians(fov) / 2)


@dataclass
class Camera:
    """Perspective camera. eye/target are world points (tracks allowed)."""

    fov: float = 30.0
    eye: object = None
    target: object = None
    aperture: object = 0.0      # CoC (design px) of an object at infinity
    focus: object = None        # focus distance; default is the eye-target distance

    def state(self, t):
        d = home_distance(self.fov)
        eye = np.array(value(self.eye, t) if self.eye is not None else (960, 540, -d), dtype=float)
        tgt = np.array(value(self.target, t) if self.target is not None else (960, 540, 0), dtype=float)
        focus = value(self.focus, t) if self.focus is not None else float(np.linalg.norm(tgt - eye))
        return eye, tgt, focus, float(value(self.aperture, t))

    def matrices(self, t):
        eye, tgt, focus, aperture = self.state(t)
        eye_g, tgt_g = FLIP[:3, :3] @ eye, FLIP[:3, :3] @ tgt
        view = _look_at(eye_g, tgt_g)
        proj = _perspective(self.fov, DESIGN[0] / DESIGN[1], 10.0, 60000.0)
        fwd = tgt_g - eye_g
        fwd /= np.linalg.norm(fwd)
        return proj, view, eye_g, fwd, focus, aperture


@dataclass
class Cursor:
    """Cursor samples in capture CSS px: list of (t, x, y, down), in source time."""

    samples: list
    viewport: tuple = (1920, 1080)
    scale: float = 1.8
    smooth: float = 0.06        # seconds, gaussian smoothing of the path
    clicks: list = field(default_factory=list)  # source times of mouse-down events

    def __post_init__(self):
        s = np.array(self.samples, dtype=float).reshape(-1, 4)
        self._t = s[:, 0]
        self._xy = s[:, 1:3]
        if not self.clicks:
            down = s[:, 3] > 0.5
            edges = np.flatnonzero(down[1:] & ~down[:-1]) + 1
            self.clicks = [float(self._t[i]) for i in edges]

    def pos(self, ts: float) -> tuple[float, float]:
        if len(self._t) == 1:
            return tuple(self._xy[0])
        # gaussian-weighted average over a small window: smooth, no lag on average
        offs = np.linspace(-2.5, 2.5, 11) * self.smooth / 2.5
        w = np.exp(-0.5 * (offs / (self.smooth / 2)) ** 2)
        xs = np.interp(ts + offs, self._t, self._xy[:, 0])
        ys = np.interp(ts + offs, self._t, self._xy[:, 1])
        return float((xs * w).sum() / w.sum()), float((ys * w).sum() / w.sum())

    def ripples(self, ts: float):
        out = [(c, ts - c) for c in self.clicks if 0 <= ts - c < 0.7]
        return out[-4:]


@dataclass
class Plane:
    """A textured rectangle, optionally dressed as a window, in world or screen space."""

    source: object              # asset key (str), or None for a still set via `image`
    start: float
    end: float
    src_in: float = 0.0         # source time at `start`
    speed: float = 1.0
    hold: float | None = None   # freeze on this source time
    size: tuple | None = None   # content size in local px (default: capture CSS size)
    chrome: str | None = None   # None, "terminal", "browser"
    title: str = ""
    radius: float = 12.0
    shadow: bool = True
    space: str = "world"        # "world" (camera) or "screen" (design px, no perspective)
    pos: object = (960.0, 540.0, 0.0)
    rot: object = (0.0, 0.0, 0.0)
    scale: object = 1.0
    opacity: object = 1.0
    blur: object = 0.0
    dim: object = 0.0
    saturation: object = 1.0
    view: object = (0.0, 0.0, 1.0, 1.0)
    cursor: Cursor | None = None
    fade_in: float = 0.0
    fade_out: float = 0.0
    name: str = ""

    titlebar_h = 40.0

    def active(self, t: float) -> bool:
        return self.start <= t < self.end

    def source_time(self, t: float) -> float:
        if self.hold is not None:
            return self.hold
        return self.src_in + (t - self.start) * self.speed

    def window_size(self, content: tuple) -> tuple:
        tb = self.titlebar_h if self.chrome else 0.0
        return content[0], content[1] + tb

    def alpha(self, t: float) -> float:
        a = float(value(self.opacity, t))
        if self.fade_in:
            a *= ramp(t, self.start, self.start + self.fade_in, "sine")
        if self.fade_out:
            a *= 1 - ramp(t, self.end - self.fade_out, self.end, "sine")
        return a

    def model(self, t: float, content: tuple) -> np.ndarray:
        W, H = self.window_size(content)
        p = value(self.pos, t)
        x, y = p[0], p[1]
        z = p[2] if len(p) > 2 else 0.0
        s = value(self.scale, t)
        sx, sy = (s, s) if not isinstance(s, tuple) else s
        rx, ry, rz = value(self.rot, t)
        return _translate(x, y, z) @ _rot(rx, ry, rz) @ _scale(sx, sy) @ _translate(-W / 2, -H / 2)

    def mvp(self, t: float, content: tuple, cam: Camera) -> np.ndarray:
        m = self.model(t, content)
        if self.space == "screen":
            return ortho_screen() @ m
        proj, view, *_ = cam.matrices(t)
        return proj @ view @ FLIP @ m


@dataclass
class Transition:
    kind: str = "cut"           # cut, dissolve, push, zoom
    dur: float = 0.0
    direction: tuple = (-1.0, 0.0)   # push: where the outgoing scene travels
    ease: str = "quint"


@dataclass
class Segment:
    name: str
    start: float
    layers: list
    camera: Camera = field(default_factory=Camera)
    trans: Transition = field(default_factory=Transition)


@dataclass
class GroupState:
    opacity: float = 1.0
    offset: tuple = (0.0, 0.0)
    zoom: float = 1.0


def group_state(seg: Segment, nxt: Segment | None, t: float) -> GroupState:
    g = GroupState()
    tr = seg.trans
    if tr.kind != "cut" and tr.dur > 0 and t < seg.start + tr.dur:
        p = ramp(t, seg.start, seg.start + tr.dur, tr.ease)
        if tr.kind == "dissolve":
            g.opacity = p
        elif tr.kind == "push":
            dx, dy = tr.direction
            g.offset = (-dx * (1 - p) * DESIGN[0], -dy * (1 - p) * DESIGN[1])
        elif tr.kind == "zoom":
            g.opacity = ramp(t, seg.start, seg.start + tr.dur * 0.7, "sine")
            g.zoom = 0.92 + 0.08 * p
    if nxt is not None:
        nt = nxt.trans
        if nt.kind != "cut" and nt.dur > 0 and t >= nxt.start:
            p = ramp(t, nxt.start, nxt.start + nt.dur, nt.ease)
            if nt.kind == "dissolve":
                g.opacity *= 1 - p
            elif nt.kind == "push":
                dx, dy = nt.direction
                g.offset = (g.offset[0] + dx * p * DESIGN[0], g.offset[1] + dy * p * DESIGN[1])
            elif nt.kind == "zoom":
                g.opacity *= 1 - ramp(t, nxt.start + nt.dur * 0.3, nxt.start + nt.dur, "sine")
                g.zoom *= 1 + 0.12 * p
    return g


@dataclass
class Timeline:
    total: float
    segments: list
    fade: object = 0.0                              # fade to black (0..1)
    background_level: object = 1.0                  # ground brightness multiplier

    def active_segments(self, t: float):
        out = []
        for i, seg in enumerate(self.segments):
            nxt = self.segments[i + 1] if i + 1 < len(self.segments) else None
            end = self.total + 1 if nxt is None else nxt.start + (nxt.trans.dur if nxt.trans.kind != "cut" else 0)
            if seg.start <= t < end:
                out.append((seg, nxt))
        return out


def keys(*k) -> Track:
    return Track(*k)
