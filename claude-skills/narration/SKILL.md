---
name: narration
description: Turn a written script into a spoken WAV with Gemini TTS (gemini-3.8-flash-tts) using a prebuilt voice and an optional style direction. Use when the user asks for narration, a voiceover, text-to-speech, an audio version of a text, or a spoken sample of a script. Covers choosing a voice, preparing the transcript, and writing style directions.
---

# Narration

`tts.py` (next to this file) sends a script to `gemini-3.8-flash-tts` and writes the returned WAV (24 kHz, mono, 16-bit PCM).

## When to use

- The user wants audio from text: a voiceover, narration, a read-aloud of a document, a demo clip, a spoken announcement.
- One narrator per file. The API supports two-speaker dialogue, but this script does not; for a dialogue, narrate each speaker's lines separately or extend the script.

Not for: transcription (speech to text), music, or sound effects.

## Running it

Needs `GEMINI_API_KEY` in the environment. `uv` installs `google-genai` from the script header on first run.

```bash
SKILL=~/.claude/skills/narration
uv run $SKILL/tts.py script.txt --voice Charon --style "calm and warm, speaking slowly" -o intro.wav
uv run $SKILL/tts.py script.txt                  # voice Kore, no style, writes script.wav
echo "Hello there." | uv run $SKILL/tts.py - -o hello.wav
uv run $SKILL/tts.py --list-voices
```

| Flag      | Meaning                                                                       |
| --------- | ----------------------------------------------------------------------------- |
| `SCRIPT`  | Transcript file, or `-` for stdin                                             |
| `--voice` | Prebuilt voice name (case-insensitive) or a `voicekey_...` id; default `Kore` |
| `--style` | Turn-level delivery direction; default none                                   |
| `-o`      | Output path; default is the script path with `.wav`                           |
| `--model` | Override the model, e.g. `gemini-3.8-flash-lite-tts`                          |

Play the result to check it (`aplay out.wav` on Linux, `afplay out.wav` on macOS, or `ffplay -autoexit out.wav`), and tell the user the file path.

Each call prints its token counts. When the skill is installed in a product-video-kit project, it also appends them to the project's `usage.jsonl` (through `tools/usage_log.py`), which `tools/costs.py` prices into `COSTS.md`.

## Choosing a voice

Pick the voice for the persona. Age, gender and accent come from the voice, never from `--style`.

| Voice     | Trait      | Voice         | Trait         | Voice        | Trait       |
| --------- | ---------- | ------------- | ------------- | ------------ | ----------- |
| Zephyr    | Bright     | Puck          | Upbeat        | Charon       | Informative |
| Kore      | Firm       | Fenrir        | Excitable     | Leda         | Youthful    |
| Orus      | Firm       | Aoede         | Breezy        | Callirrhoe   | Easy-going  |
| Autonoe   | Bright     | Enceladus     | Breathy       | Iapetus      | Clear       |
| Umbriel   | Easy-going | Algieba       | Smooth        | Despina      | Smooth      |
| Erinome   | Clear      | Algenib       | Gravelly      | Rasalgethi   | Informative |
| Laomedeia | Upbeat     | Achernar      | Soft          | Alnilam      | Firm        |
| Schedar   | Even       | Gacrux        | Mature        | Pulcherrima  | Forward     |
| Achird    | Friendly   | Zubenelgenubi | Casual        | Vindemiatrix | Gentle      |
| Sadachbia | Lively     | Sadaltager    | Knowledgeable | Sulafat      | Warm        |

Starting points: explainers and documentation `Charon`, `Sadaltager`, `Iapetus`; product demos `Puck`, `Achird`; bedtime or meditation `Sulafat`, `Vindemiatrix`, `Achernar`; announcements `Kore`, `Alnilam`; storytelling `Gacrux`, `Algenib`.

## Writing the script

The model reads the file as a verbatim transcript: every word in it is spoken. Never put directions ("read this cheerfully") in the script; they go in `--style`.

- **Pacing**: punctuation does most of it. Commas and dashes give short breaks, ellipses trail off, paragraph breaks give longer ones. Add `<short pause>` or `<long pause>` where timing matters.
- **Emphasis**: capitalise the word and back it with punctuation: `This is a VERY important point!`
- **Momentary sounds**: inline tags at the exact point they happen: `<breath>`, `<sigh>`, `<laugh>`, `<gasp>`, `<cough>`, `<throat-clearing>`.
- **Written forms**: spell out what should be said aloud. Write `twenty twenty-six` if `2026` might read wrong, expand abbreviations the listener would not hear as letters, and drop markdown, URLs and code blocks.
- **Language**: write in the target language; the model supports over 130 and follows the text.

```text
Welcome back. <short pause> Today we're looking at something small... but it matters.

Every build you run — every single one — starts here. <breath> And most people never look at it.
```

## Writing style directions

`--style` sets sustained delivery for the whole file. Start with no style at all: most scripts need none, and the voice plus punctuation carries them. Add a style only when a listen shows the delivery is wrong.

A good direction is a few words naming tone, energy and pace:

| Good                              | Why                            |
| --------------------------------- | ------------------------------ |
| `calm and relaxed`                | Tone and energy, nothing else  |
| `cheerful and friendly`           | Two compatible attributes      |
| `speaking slowly, warm`           | Pace plus tone                 |
| `whispers`                        | A single sustained delivery    |
| `sarcastic`                       | An attitude the model can hold |
| `speaking rapidly, out of breath` | Pace plus physical state       |

Avoid:

| Bad                                          | Problem                                                                                    |
| -------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `a 60-year-old British man`                  | Age, gender and accent belong to the voice choice                                          |
| `keep the voice steady throughout`           | The docs say not to give instructions to hold the voice steady                             |
| `start excited, then get sad at the end`     | Style is one sustained delivery; split the script into separate files for a change of mood |
| `pause after the second sentence`            | Point-in-time events go in the script as tags                                              |
| A paragraph of scene, backstory and audience | Long style blocks dilute the direction; keep it to a short phrase                          |

When iterating, change one thing at a time (voice, then style, then script punctuation) and listen after each.

## Long scripts

The docs give no input length limit. If the audio stops early or drifts, split the script at paragraph boundaries, narrate each part with the same voice and style, and join them:

```bash
sox part1.wav part2.wav part3.wav full.wav
```
