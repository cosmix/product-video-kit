"""Easing and timing helpers. Scenes are authored in nominal seconds; every
transition goes through one of these so nothing reads linear."""

import math


def clamp01(x):
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def seg(t, a, b):
    """Normalised progress of t through [a, b], clamped to [0, 1]."""
    if b <= a:
        return 1.0 if t >= b else 0.0
    return clamp01((t - a) / (b - a))


def lerp(a, b, u):
    return a + (b - a) * u


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def cubic_io(u):
    u = clamp01(u)
    return 4 * u * u * u if u < 0.5 else 1 - ((-2 * u + 2) ** 3) / 2


def quint_io(u):
    u = clamp01(u)
    return 16 * u ** 5 if u < 0.5 else 1 - ((-2 * u + 2) ** 5) / 2


def cubic_out(u):
    u = clamp01(u)
    return 1 - (1 - u) ** 3


def quint_out(u):
    u = clamp01(u)
    return 1 - (1 - u) ** 5


def cubic_in(u):
    u = clamp01(u)
    return u * u * u


def expo_out(u):
    u = clamp01(u)
    return 1.0 if u >= 1.0 else 1 - 2 ** (-10 * u)


def back_out(u, s=1.25):
    """Overshoot capped around 4 % (s=1.25 gives ~3.7 %)."""
    u = clamp01(u)
    return 1 + (s + 1) * (u - 1) ** 3 + s * (u - 1) ** 2


def spring(u, zeta=0.62, omega=11.0):
    """Underdamped step response, settles at 1 with a small overshoot."""
    u = clamp01(u)
    if u >= 1.0:
        return 1.0
    wd = omega * math.sqrt(1 - zeta * zeta)
    return 1 - math.exp(-zeta * omega * u) * (
        math.cos(wd * u) + (zeta / math.sqrt(1 - zeta * zeta)) * math.sin(wd * u)
    )


def pulse(u, width=0.5):
    """0 → 1 → 0 hump over [0, 1] with smooth shoulders."""
    u = clamp01(u)
    return math.sin(math.pi * u) ** (1.0 / max(width, 1e-3)) if u > 0 else 0.0


def stagger(t, i, start, step, length):
    """Progress of item i whose window opens at start + i * step."""
    return seg(t, start + i * step, start + i * step + length)


def wave(t, freq=1.0, phase=0.0):
    return 0.5 + 0.5 * math.sin(2 * math.pi * freq * t + phase)


def ease_in_linear(u, k=0.35):
    """Accelerates over the first k, then moves at constant speed to the end
    (no deceleration): for a light that passes through and leaves."""
    u = clamp01(u)
    e = u * u / (2 * k) if u < k else u - k / 2
    return e / (1 - k / 2)
