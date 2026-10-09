"""Easing curves and keyframed tracks.

A Track holds (time, value, ease) keys; the ease on a key shapes the segment that ENDS at
that key. Values may be floats or tuples (interpolated component-wise).
"""

import math
from bisect import bisect_right


def linear(x: float) -> float:
    return x


def cubic_in_out(x: float) -> float:
    return 4 * x * x * x if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def quint_in_out(x: float) -> float:
    return 16 * x**5 if x < 0.5 else 1 - (-2 * x + 2) ** 5 / 2


def cubic_out(x: float) -> float:
    return 1 - (1 - x) ** 3


def quint_out(x: float) -> float:
    return 1 - (1 - x) ** 5


def cubic_in(x: float) -> float:
    return x * x * x


def sine_in_out(x: float) -> float:
    return -(math.cos(math.pi * x) - 1) / 2


def spring(x: float, overshoot: float = 0.035) -> float:
    """Critically-underdamped settle: reaches 1 with a single overshoot of about `overshoot`."""
    if x >= 1:
        return 1.0
    # damped cosine tuned so the first peak is ~overshoot and the tail is negligible at x=1
    zeta = -math.log(overshoot) / math.sqrt(math.pi**2 + math.log(overshoot) ** 2)
    wn = 9.0
    wd = wn * math.sqrt(1 - zeta * zeta)
    e = math.exp(-zeta * wn * x)
    return 1 - e * (math.cos(wd * x) + zeta * wn / wd * math.sin(wd * x))


EASES = {
    "linear": linear,
    "cubic": cubic_in_out,
    "quint": quint_in_out,
    "out": cubic_out,
    "quint_out": quint_out,
    "in": cubic_in,
    "sine": sine_in_out,
    "spring": spring,
}


def smoothstep(e0: float, e1: float, x: float) -> float:
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def ramp(t: float, t0: float, t1: float, ease: str = "cubic") -> float:
    """0 before t0, 1 after t1, eased in between."""
    if t <= t0:
        return 0.0
    if t >= t1:
        return 1.0
    return EASES[ease]((t - t0) / (t1 - t0))


def _lerp(a, b, k):
    if isinstance(a, tuple):
        return tuple(x + (y - x) * k for x, y in zip(a, b))
    return a + (b - a) * k


class Track:
    """Piecewise keyframe track. keys: iterable of (t, value) or (t, value, ease)."""

    def __init__(self, *keys):
        norm = [(k[0], k[1], k[2] if len(k) > 2 else "cubic") for k in keys]
        norm.sort(key=lambda k: k[0])
        self.times = [k[0] for k in norm]
        self.values = [k[1] for k in norm]
        self.eases = [k[2] for k in norm]

    def __call__(self, t: float):
        i = bisect_right(self.times, t)
        if i == 0:
            return self.values[0]
        if i == len(self.times):
            return self.values[-1]
        t0, t1 = self.times[i - 1], self.times[i]
        k = EASES[self.eases[i]]((t - t0) / (t1 - t0))
        return _lerp(self.values[i - 1], self.values[i], k)

    def shifted(self, dt: float) -> "Track":
        return Track(*[(t + dt, v, e) for t, v, e in zip(self.times, self.values, self.eases)])


def const(v) -> Track:
    return Track((0.0, v))


def value(v, t: float):
    """Evaluate a property that may be a Track, a callable, or a constant."""
    if isinstance(v, Track) or callable(v):
        return v(t)
    return v
