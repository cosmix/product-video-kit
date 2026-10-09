"""Word-level timings for the narration, from faster-whisper, placed on the master timeline.

Writes build/words.json: {section: [{"w": word, "start": s, "end": s}, ...]} with times in
master-timeline seconds. The EDL uses it to put on-screen events under spoken words and
subs.py uses it to time subtitle cues. A video without narration gets an empty file.

Usage: uv run words.py
"""

import json
import os
from pathlib import Path

import soundfile as sf
from faster_whisper import WhisperModel
from scipy.signal import resample_poly

from editkit.shots import timeline

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "build" / "words.json"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not timeline()["narration"]:
        OUT.write_text("{}")
        print(f"no narration in narration/timeline.json: wrote an empty {OUT}")
        return
    model = WhisperModel("deepdml/faster-whisper-large-v3-turbo-ct2", device="cpu", compute_type="int8",
                          cpu_threads=os.cpu_count() or 4)
    result = {}
    for sec in timeline()["narration"]:
        audio, sr = sf.read(ROOT / sec["file"], dtype="float32", always_2d=True)
        audio = resample_poly(audio.mean(axis=1), 16000, sr).astype("float32")
        segments, _ = model.transcribe(audio, language=None, word_timestamps=True, beam_size=5)
        words = []
        for seg in segments:
            for w in seg.words:
                words.append(
                    {"w": w.word.strip(), "start": round(sec["start"] + w.start, 3),
                     "end": round(sec["start"] + w.end, 3)}
                )
        result[sec["name"]] = words
        print(sec["name"], " ".join(w["w"] for w in words))
    OUT.write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
