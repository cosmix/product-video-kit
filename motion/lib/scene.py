"""Scene base: authored in nominal seconds, retimed uniformly by --duration.

A project scene is a module motion/scenes/<name>.py that defines SCENE, a Scene subclass
(README.md, "Motion graphics")."""


class Scene:
    name = "scene"      # output file stem; use the module name
    key = None          # the timeline scene key it belongs to (for the manifest)
    nominal = 10.0      # authored length in seconds: the locked window from timeline.json
    alpha = False       # True: the scene is transparent by default (ProRes 4444 .mov)
    marks = []          # [(nominal_t, event)]

    def __init__(self, duration=None):
        self.duration = duration or self.nominal
        self.rate = self.nominal / self.duration
        self.setup()

    def setup(self):
        """Build state that does not depend on time (fonts, paths, layouts); optional."""

    def u(self, t):
        """Nominal time for wall time t."""
        return t * self.rate

    def draw(self, canvas, t, opaque):
        raise NotImplementedError(f"{type(self).__name__} must define draw(canvas, t, opaque)")

    def scaled_marks(self):
        return [{"t": round(mt / self.rate, 3), "event": ev} for mt, ev in self.marks]
