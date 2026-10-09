#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "google-genai>=2.25.0",
# ]
# ///
"""Narrate a script file with Gemini TTS and save the result as a WAV.

Usage:
    uv run tts.py SCRIPT [--voice NAME] [--style TEXT] [-o OUT.wav]

SCRIPT is a text file (or '-' for stdin) read as a verbatim transcript:
inline tags such as <short pause> or <laugh> are performed, not spoken.
Requires GEMINI_API_KEY (or GOOGLE_API_KEY) in the environment.
"""

import argparse
import base64
import os
import sys
from pathlib import Path

from google import genai

MODEL = "gemini-3.8-flash-tts"

VOICES = {
    "Zephyr": "Bright",
    "Puck": "Upbeat",
    "Charon": "Informative",
    "Kore": "Firm",
    "Fenrir": "Excitable",
    "Leda": "Youthful",
    "Orus": "Firm",
    "Aoede": "Breezy",
    "Callirrhoe": "Easy-going",
    "Autonoe": "Bright",
    "Enceladus": "Breathy",
    "Iapetus": "Clear",
    "Umbriel": "Easy-going",
    "Algieba": "Smooth",
    "Despina": "Smooth",
    "Erinome": "Clear",
    "Algenib": "Gravelly",
    "Rasalgethi": "Informative",
    "Laomedeia": "Upbeat",
    "Achernar": "Soft",
    "Alnilam": "Firm",
    "Schedar": "Even",
    "Gacrux": "Mature",
    "Pulcherrima": "Forward",
    "Achird": "Friendly",
    "Zubenelgenubi": "Casual",
    "Vindemiatrix": "Gentle",
    "Sadachbia": "Lively",
    "Sadaltager": "Knowledgeable",
    "Sulafat": "Warm",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Narrate a script with Gemini TTS.")
    parser.add_argument("script", nargs="?", help="transcript file, or '-' for stdin")
    parser.add_argument(
        "--voice",
        default="Kore",
        help="prebuilt voice name or a voicekey_... id (default: Kore)",
    )
    parser.add_argument(
        "--style",
        default="",
        help="turn-level delivery, e.g. 'calm and warm, speaking slowly'",
    )
    parser.add_argument(
        "-o", "--output", help="output WAV path (default: SCRIPT with .wav suffix)"
    )
    parser.add_argument("--model", default=MODEL, help=f"TTS model (default: {MODEL})")
    parser.add_argument(
        "--list-voices", action="store_true", help="print the prebuilt voices and exit"
    )
    args = parser.parse_args()
    if not args.list_voices and not args.script:
        parser.error("SCRIPT is required")
    return args


def resolve_voice(name: str) -> str:
    if name.startswith("voicekey_"):
        return name
    for voice in VOICES:
        if voice.lower() == name.lower():
            return voice
    sys.exit(f"error: unknown voice '{name}'; run with --list-voices")


def read_script(path: str) -> str:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    text = text.strip()
    if not text:
        sys.exit("error: script is empty")
    return text


def output_path(script: str, output: str | None) -> Path:
    if output:
        return Path(output)
    if script == "-":
        return Path("narration.wav")
    return Path(script).with_suffix(".wav")


def synthesize(model: str, text: str, voice: str, style: str) -> bytes:
    content: dict[str, object] = {"type": "text", "text": text}
    if style:
        content["annotations"] = [{"type": "speech_metadata", "style": style}]
    client = genai.Client()
    interaction = client.interactions.create(
        model=model,
        input=[{"type": "user_input", "content": [content]}],
        response_format={"type": "audio"},
        generation_config={"speech_config": [{"voice": voice}]},
    )
    audio = base64.b64decode(interaction.output_audio.data)
    if audio[:4] != b"RIFF":
        sys.exit("error: response is not a WAV (missing RIFF header)")
    return audio


def main() -> None:
    args = parse_args()
    if args.list_voices:
        for voice, trait in VOICES.items():
            print(f"{voice:<15} {trait}")
        return
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        sys.exit("error: set GEMINI_API_KEY")
    voice = resolve_voice(args.voice)
    text = read_script(args.script)
    out = output_path(args.script, args.output)
    audio = synthesize(args.model, text, voice, args.style)
    out.write_bytes(audio)
    print(f"{out} ({len(audio):,} bytes, voice {voice})")


if __name__ == "__main__":
    main()
