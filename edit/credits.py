"""Credits for the video description, from the same data as the on-screen credits.

Usage: uv run credits.py        -> out/CREDITS.txt
"""

from pathlib import Path

from editkit import credit_data as cd
from editkit.project import edl

OUT = Path(__file__).resolve().parent / "out" / "CREDITS.txt"


def main() -> None:
    lines = [cd.title(), ""] if cd.title() else []
    if broll := cd.broll(list(getattr(edl(), "BROLL_CLIPS", []))):
        lines += ["B-roll (Creative Commons Attribution):"]
        lines += [f"- \"{c.title}\", {c.by}, {c.url} ({c.licence})" for c in broll] + [""]
    if samples := cd.music_samples():
        lines += ["Music: original score, with samples from"]
        lines += [f"- {c.title}, {c.by} ({c.licence}) {c.url}".rstrip() for c in samples]
    lines += [f"{label}: {text}" for label, text in cd.extra_rows()]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    if lines:
        print(f"wrote {OUT}")
    else:
        print(f"nothing to credit (no music, b-roll or credits.json rows): wrote an empty {OUT}")


if __name__ == "__main__":
    main()
