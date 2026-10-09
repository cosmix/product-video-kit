"""Deterministic frame stepping: one virtual 1/60 s per captured frame.

Per frame: advance the mock server's clock, wait until the page has received
every frame the server sent, advance the page's faked clock (timers, rAF,
Date, performance.now), dispatch this frame's input, seek every CSS
animation and transition to the same virtual time, then screenshot. Nothing
depends on how long a screenshot takes, so motion is exactly 60 fps.
"""

from __future__ import annotations

import asyncio
import base64
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from playwright.async_api import Page

from webcap.world import World

FPS = 60

INIT_SCRIPT = r"""
(() => {
  // the project's LOCAL_STORAGE (theme and similar settings), set before the app reads it
  try {
    for (const [key, value] of Object.entries(__STORAGE__)) {
      localStorage.setItem(key, JSON.stringify(value));
    }
  } catch (_) {}
  // Headless reports notifications as blocked whatever the grant; show the
  // ordinary "off" switch a desktop browser shows instead of that warning.
  if (window.Notification) {
    Object.defineProperty(Notification, "permission", { get: () => "granted" });
  }
  window.__rx = 0;
  const Native = window.WebSocket;
  class Counted extends Native {
    constructor(...args) {
      super(...args);
      this.addEventListener("message", () => { window.__rx += 1; });
    }
  }
  window.WebSocket = Counted;
  const births = new WeakMap();
  window.__syncAnimations = () => {
    const now = performance.now();
    for (const a of document.getAnimations()) {
      let born = births.get(a);
      if (born === undefined) { born = now; births.set(a, born); }
      const local = (now - born) * (a.playbackRate || 1);
      const end = a.effect ? a.effect.getComputedTiming().endTime : Infinity;
      if (Number.isFinite(end) && local >= end) {
        if (a.playState !== "finished") a.finish();
        continue;
      }
      if (a.playState !== "paused") a.pause();
      a.currentTime = local;
    }
  };
  // The native caret blinks on a real-time timer, which frame stepping turns
  // into flicker. Hide it and draw one on the virtual clock: solid for 500 ms
  // after focus or input, then 500 ms on / 500 ms off, as Chrome does.
  const caret = document.createElement("div");
  caret.style.cssText = "position:fixed;width:1px;pointer-events:none;z-index:2147483647;display:none";
  const measure = document.createElement("canvas").getContext("2d");
  let typedAt = 0;
  const stamp = () => { typedAt = performance.now(); };
  document.addEventListener("input", stamp, true);
  document.addEventListener("focusin", stamp, true);
  const TEXT = new Set(["text", "search", "email", "url", ""]);
  window.__drawCaret = () => {
    const el = document.activeElement;
    if (!(el instanceof HTMLInputElement) || !TEXT.has(el.type) || el.selectionStart !== el.selectionEnd) {
      caret.style.display = "none";
      return;
    }
    if (!caret.isConnected) document.body.appendChild(caret);
    const cs = getComputedStyle(el);
    // cs.font is empty when the font shorthand cannot express the computed
    // style, so assemble it.
    measure.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    measure.letterSpacing = cs.letterSpacing;
    const rect = el.getBoundingClientRect();
    const size = parseFloat(cs.fontSize);
    const height = Math.round(size * 1.2);
    const x = rect.left + parseFloat(cs.borderLeftWidth) + parseFloat(cs.paddingLeft)
      + measure.measureText(el.value.slice(0, el.selectionStart)).width - el.scrollLeft;
    const on = (performance.now() - typedAt) % 1000 < 500;
    caret.style.display = on ? "block" : "none";
    caret.style.left = `${x}px`;
    caret.style.top = `${rect.top + (rect.height - height) / 2}px`;
    caret.style.height = `${height}px`;
    caret.style.background = cs.color;
  };
  window.__frame = () => { window.__syncAnimations(); window.__drawCaret(); };
  const hide = () => {
    const style = document.createElement("style");
    style.textContent = "*{scrollbar-width:none!important}*::-webkit-scrollbar{display:none!important}" +
      ".xterm .scrollbar{opacity:0!important}input{caret-color:transparent!important}";
    document.head.appendChild(style);
  };
  if (document.head) hide(); else document.addEventListener("DOMContentLoaded", hide);
})();
"""


def ease_cubic(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 4 * u**3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


@dataclass
class Clip:
    name: str
    out_dir: Path
    frames: int = 0
    marks: list[dict] = field(default_factory=list)
    cursor: list[dict] = field(default_factory=list)
    stills: list[str] = field(default_factory=list)

    @property
    def path(self) -> Path:
        return self.out_dir / f"{self.name}.mp4"

    @property
    def partial(self) -> Path:
        """Where the encode runs; renamed onto `path` only once complete."""
        return self.out_dir / f"{self.name}.tmp.mp4"


class Director:
    def __init__(self, page: Page, world: World, out_dir: Path, scale: float) -> None:
        self.page = page
        self.scale = scale
        self.draft = scale < 2
        self.world = world
        self.out_dir = out_dir
        self.frame = 0  # virtual frame index; t = frame / FPS
        self.x, self.y = 960.0, 540.0
        self.down = False
        self.clip: Clip | None = None
        self._ffmpeg: subprocess.Popen | None = None
        self._cdp = None
        self._offset = 0
        self._last_png: bytes | None = None

    @property
    def t(self) -> float:
        return self.frame / FPS

    async def setup(self) -> None:
        self._cdp = await self.page.context.new_cdp_session(self.page)

    # --- recording -------------------------------------------------------

    def start(self, name: str) -> None:
        """Begin a clip; frames captured from here are its frames."""
        self.clip = Clip(name, self.out_dir)
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS),
            "-c:v", "png", "-i", "-",
            "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
            "-c:v", "libx264", "-preset", "ultrafast" if self.draft else "slow",
            "-crf", "23" if self.draft else "10", "-pix_fmt", "yuv420p",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-color_range", "tv", "-r", str(FPS), "-movflags", "+faststart", str(self.clip.partial),
        ]
        self._ffmpeg = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        self._clip_origin = self.frame

    def finish(self) -> Clip:
        clip = self.clip
        self._ffmpeg.stdin.close()
        if self._ffmpeg.wait() != 0:
            raise RuntimeError(f"ffmpeg failed for {clip.name}")
        clip.partial.replace(clip.path)
        self.clip, self._ffmpeg = None, None
        return clip

    @property
    def clip_origin(self) -> float:
        """Virtual time of the clip's first frame."""
        return self._clip_origin / FPS

    def clip_t(self) -> float:
        return round((self.frame - self._clip_origin) / FPS, 4)

    def mark(self, event: str, key: bool = False) -> None:
        """Log an event; key marks are the ones the edit syncs narration to."""
        if self.clip:
            entry = {"t": self.clip_t(), "event": event}
            if key:
                entry["key"] = True
            self.clip.marks.append(entry)

    def still(self, name: str) -> None:
        path = self.out_dir / f"{name}.png"
        partial = path.with_suffix(".tmp.png")
        partial.write_bytes(self._last_png)
        partial.replace(path)
        if self.clip:
            self.clip.stills.append(path.name)
            self.mark(f"still {path.name}")

    # --- the frame step --------------------------------------------------

    async def _sync_messages(self) -> None:
        target = self.world.sent
        seen, stable = -1, 0
        for _ in range(80):
            rx = await self.page.evaluate("window.__rx")
            if rx + self._offset >= target:
                return
            stable = stable + 1 if rx == seen else 0
            seen = rx
            if stable >= 6:
                # A frame sent to a socket the page already closed never
                # arrives; rebase instead of waiting on it forever.
                self._offset = target - rx
                return
            await asyncio.sleep(0.003)

    async def step(self, actions=None) -> None:
        """Render one frame at the current virtual time, then advance it."""
        await self.world.tick(self.t)
        await self._sync_messages()
        ms = round((self.frame + 1) * 1000 / FPS) - round(self.frame * 1000 / FPS)
        await self.page.clock.run_for(ms)
        if actions:
            await actions()
        await self.page.evaluate("window.__frame()")
        if self.clip:
            # A CDP session of our own does not inherit Playwright's device
            # metrics, so ask for the device scale explicitly.
            clip = {"x": 0, "y": 0, "width": 1920, "height": 1080, "scale": self.scale}
            shot = await self._cdp.send(
                "Page.captureScreenshot", {"format": "png", "optimizeForSpeed": True, "clip": clip}
            )
            self._last_png = base64.b64decode(shot["data"])
            self._ffmpeg.stdin.write(self._last_png)
            self.clip.frames += 1
            self.clip.cursor.append(
                {"t": self.clip_t(), "x": round(self.x, 1), "y": round(self.y, 1), "down": self.down}
            )
        self.frame += 1
        # Let the loop deliver whatever the page sent back (keystrokes, resizes).
        await asyncio.sleep(0)

    # --- choreography ----------------------------------------------------

    async def hold(self, seconds: float) -> None:
        for _ in range(round(seconds * FPS)):
            await self.step()

    async def glide(self, x: float, y: float, seconds: float, arc: float = 0.08) -> None:
        """Move the pointer along a gently bowed, eased path."""
        x0, y0 = self.x, self.y
        n = max(1, round(seconds * FPS))
        dx, dy = x - x0, y - y0
        dist = math.hypot(dx, dy)
        nx, ny = (-dy / dist, dx / dist) if dist else (0.0, 0.0)
        for i in range(1, n + 1):
            u = ease_cubic(i / n)
            bow = math.sin(math.pi * u) * arc * dist
            px, py = x0 + dx * u + nx * bow, y0 + dy * u + ny * bow

            async def move(px=px, py=py):
                self.x, self.y = px, py
                await self.page.mouse.move(px, py)

            await self.step(move)

    async def click(self, count: int = 1, hold_frames: int = 5, gap_frames: int = 7) -> None:
        for n in range(1, count + 1):
            async def press(n=n):
                self.down = True
                await self.page.mouse.down(click_count=n)

            async def release(n=n):
                self.down = False
                await self.page.mouse.up(click_count=n)

            await self.step(press)
            for _ in range(hold_frames - 1):
                await self.step()
            await self.step(release)
            if n < count:
                for _ in range(gap_frames):
                    await self.step()
        self.mark("double-click" if count == 2 else "click")

    async def type(self, text: str, cps: float = 13.0, jitter: float = 0.35) -> None:
        """Type at a human pace: a steady rhythm with a deterministic wobble."""
        for i, ch in enumerate(text):
            async def key(ch=ch):
                await self.page.keyboard.type(ch)

            await self.step(key)
            wobble = 1 + jitter * math.sin(i * 2.3 + 0.7) * math.cos(i * 0.9)
            pause = (1 / cps) * wobble + (0.12 if ch == " " and i % 3 == 0 else 0)
            for _ in range(max(1, round(pause * FPS)) - 1):
                await self.step()

    async def press(self, key: str) -> None:
        async def action():
            await self.page.keyboard.press(key)

        await self.step(action)

    async def center(self, selector: str) -> tuple[float, float]:
        box = await self.page.locator(selector).first.bounding_box()
        if box is None:
            raise RuntimeError(f"not visible: {selector}")
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
