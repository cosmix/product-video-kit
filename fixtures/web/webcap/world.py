"""The scripted clock a capture runs on, and the base of the project's mock server state.

The capture driver owns time: it calls `World.tick(t)` once per video frame, and every message
the page receives must follow from that clock. A project subclasses World in
fixtures/web/product.py (README.md, "Web capture"), sends every WebSocket message through
`send()` so the director can wait until the page has received it, and overrides `set_scene` and
`tick` to publish its fixture story.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

EPOCH = datetime(2026, 1, 15, 9, 30, tzinfo=timezone.utc)   # default page wall clock at story second 0


@dataclass(frozen=True)
class Clock:
    """Piecewise-linear map from clip seconds to story seconds: ((clip_t, story_s), ...).
    `epoch` is the page's wall clock at story second 0 (dates and "x min ago" labels)."""

    points: tuple[tuple[float, float], ...]
    epoch: datetime = EPOCH

    def __call__(self, t: float) -> float:
        pts = self.points
        if t <= pts[0][0]:
            return pts[0][1]
        for (t0, s0), (t1, s1) in zip(pts, pts[1:]):
            if t <= t1:
                return s0 + (s1 - s0) * (t - t0) / (t1 - t0)
        (t0, s0), (t1, s1) = pts[-2], pts[-1]
        return s1 + (s1 - s0) * (t - t1) / (t1 - t0)

    def inverse(self, s: float) -> float | None:
        """First clip second at which story second `s` is reached."""
        for (t0, s0), (t1, s1) in zip(self.points, self.points[1:]):
            if s0 <= s <= s1 and s1 > s0:
                return t0 + (t1 - t0) * (s - s0) / (s1 - s0)
        (t0, s0), (t1, s1) = self.points[-2], self.points[-1]
        return t1 + (s - s1) * (t1 - t0) / (s1 - s0) if s > s1 else None

    def epoch_ms(self) -> int:
        """Page wall clock at clip t = 0."""
        return int((self.epoch + timedelta(seconds=self(0.0))).timestamp() * 1000)


class World:
    """Clip time, the scene's clock and the count of messages sent to the page."""

    def __init__(self, scenes: dict[str, Clock]) -> None:
        self.scenes = scenes
        self.scene = next(iter(scenes))
        self.t = 0.0
        self.sent = 0

    @property
    def clock(self) -> Clock:
        return self.scenes[self.scene]

    def story_s(self) -> float:
        return self.clock(self.t)

    def set_scene(self, name: str) -> None:
        """Start a scene from clean state; a subclass resets its own state too."""
        if name not in self.scenes:
            raise KeyError(f"no scene {name!r} (have {', '.join(self.scenes)})")
        self.scene = name
        self.t = 0.0

    async def tick(self, t: float) -> None:
        """Advance to clip time t; a subclass publishes whatever changed through send()."""
        self.t = t

    async def send(self, ws, data: str | bytes) -> None:
        """Send one WebSocket message (an aiohttp WebSocketResponse) and count it."""
        if ws.closed:
            return
        try:
            if isinstance(data, bytes):
                await ws.send_bytes(data)
            else:
                await ws.send_str(data)
            self.sent += 1
        except ConnectionError:
            pass
