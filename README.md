# Product Video Kit

Humans start with [HUMAN.md](HUMAN.md); agents start with `CLAUDE.md`.

This kit makes a two-to-three-minute intro or demo video for a piece of software from code alone:
narration, an original score, motion graphics, captures of the product, generated b-roll, and a
GPU compositor that assembles the cut. A team of Claude Code agents does the work while one human
reviews and steers. Nothing is edited by hand in a video editor; every frame comes from code that
can be re-run.

The kit is the engine and this guide. It holds no video: the script, the score, the scenes, the
capture choreography and the edit decision list are code and data the team writes for your
product, each against a small interface the engine loads. [Pipeline and folder
map](#pipeline-and-folder-map) separates the engine from the files a project writes, and each
[workstream guide](#workstream-guides) gives a file's format, the engine helpers to call and the
pitfalls a finished video ran into. Each renderer has a self-test that runs with no project files.

## Contents

- [Product Video Kit](#product-video-kit)
  - [Contents](#contents)
  - [What you make](#what-you-make)
    - [The stack](#the-stack)
  - [How the kit is used](#how-the-kit-is-used)
  - [Requirements](#requirements)
  - [Setup](#setup)
    - [Install into a project](#install-into-a-project)
    - [System packages](#system-packages)
    - [What has been verified](#what-has-been-verified)
    - [Running on macOS](#running-on-macos)
    - [CPU-only machines](#cpu-only-machines)
  - [The team](#the-team)
    - [Rules that make the team work](#rules-that-make-the-team-work)
    - [Good briefs](#good-briefs)
  - [The workflow](#the-workflow)
    - [Phase 0: kickoff](#phase-0-kickoff)
    - [Phase 1: the timeline first](#phase-1-the-timeline-first)
    - [Phase 2: the shared spec and the briefs](#phase-2-the-shared-spec-and-the-briefs)
    - [Phase 3: production](#phase-3-production)
    - [Phase 4: the review loop](#phase-4-the-review-loop)
    - [Phase 5: finishing](#phase-5-finishing)
    - [A reusable plan](#a-reusable-plan)
  - [Pipeline and folder map](#pipeline-and-folder-map)
    - [Engine and project files](#engine-and-project-files)
  - [Code that needs your product](#code-that-needs-your-product)
  - [Deliverable conventions](#deliverable-conventions)
  - [Workstream guides](#workstream-guides)
    - [Narration](#narration)
    - [The listening judge](#the-listening-judge)
    - [Music](#music)
    - [Motion graphics](#motion-graphics)
    - [Web capture](#web-capture)
    - [TUI capture](#tui-capture)
    - [B-roll](#b-roll)
    - [The edit](#the-edit)
    - [The mix](#the-mix)
    - [Subtitles and credits](#subtitles-and-credits)
  - [Brand](#brand)
    - [`BRAND.md` and `brand/`](#brandmd-and-brand)
    - [The brand skill](#the-brand-skill)
    - [The checker](#the-checker)
    - [The logo in a scene](#the-logo-in-a-scene)
  - [Design system](#design-system)
    - [Defining the design](#defining-the-design)
    - [`design.json`](#designjson)
    - [Fonts by family](#fonts-by-family)
    - [Who reads what](#who-reads-what)
    - [Legibility](#legibility)
    - [Rejected styles](#rejected-styles)
    - [Transitions](#transitions)
  - [Editorial rules](#editorial-rules)
  - [Review and QA](#review-and-qa)
    - [How the lead reviews without watching](#how-the-lead-reviews-without-watching)
    - [QA checklist (every master)](#qa-checklist-every-master)
  - [Encoding](#encoding)
    - [The master](#the-master)
    - [The share copy](#the-share-copy)
  - [Project records](#project-records)
    - [`NOTES.md`: the decision log](#notesmd-the-decision-log)
    - [`edit/ISSUES.md`: the editor's issue log](#editissuesmd-the-editors-issue-log)
    - [`HANDBOOK.md`: the project's own handbook](#handbookmd-the-projects-own-handbook)
  - [Mistakes and pitfalls](#mistakes-and-pitfalls)
  - [Snippets](#snippets)
  - [Licences and credits](#licences-and-credits)

## What you make

A video of about three minutes at 1920x1080 and 60 fps with:

- a narrator (Gemini TTS) reading a script the human and the lead agent write together;
- an original score composed as Python code and rendered from free sample libraries;
- motion graphics drawn with skia-python on the GPU, including the product's logo from its SVG or
  PNG;
- real captures of the product: its web UI (the real built frontend, driven by a mock server with
  fixture data), its terminal UIs (the real binary in a pseudo-terminal) and real CLI output;
- b-roll generated with Gemini Omni;
- a GPU compositor in Python (moderngl) that places everything on 3D planes with window chrome,
  depth of field, motion blur and grading, mixes the audio, and writes subtitles and credits.

Narration, the score and b-roll are each optional, chosen at kickoff. Without narration the
sections are timed from their on-screen text or from set durations and there are no subtitles;
without music the mix is sound design alone; without b-roll the cut uses motion graphics and
captures. With none of the three the video is motion graphics and captures over sound design.

### The stack

| Need                | Tool                                                                                                                                                          |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Team                | Claude Code: one lead session plus named background subagents that message each other                                                                         |
| Narration           | `gemini-3.8-flash-tts` through the `narration` Claude Code skill (`tts.py`)                                                                                   |
| Ears for the agents | `tools/listen.py`: uploads audio or video to a Gemini model and asks questions about it                                                                       |
| Music               | numpy/scipy sample playback, `pedalboard` for reverb and mastering, `pyloudnorm` for loudness; Salamander Grand Piano (CC BY 3.0) and VSCO-2 CE (CC0) samples |
| Motion graphics     | skia-python (vector drawing, text, the logo), on the GPU through a moderngl OpenGL context (headless EGL on Linux, CGL on macOS)                              |
| Web UI capture      | a Python aiohttp mock of the product's server plus Playwright (Chromium), deterministic frame stepping                                                        |
| Terminal capture    | the real CLI in a pty (`ptyprocess`), `pyte` as the terminal emulator, skia to draw each screen                                                               |
| B-roll              | Gemini Omni (`gemini-omni-1.1-flash`) through `tools/genvideo.py`, prompts in `broll/gen/shots.json`                                                          |
| Word timings        | `faster-whisper` on the narration                                                                                                                             |
| Compositing         | moderngl and GLSL shaders, frames piped to ffmpeg                                                                                                             |
| Encoding and QA     | ffmpeg (`ebur128`, `signalstats`, `silencedetect`, tile filters for contact sheets)                                                                           |
| Environments        | one `uv` project per workstream                                                                                                                               |

## How the kit is used

One kit serves many videos. The kit folder holds the engine, this guide, `HUMAN.md`, `CLAUDE.md`
and the Claude Code skills; nobody works inside it. For each video:

1. The human runs `./install.sh <project-dir>` from the kit folder. It creates the project folder:
   the engine, `README.md`, `HUMAN.md`, `CLAUDE.md`, and the skills copied into `.claude/skills/`
   ([Install into a project](#install-into-a-project)). It refuses a target inside the kit
   folder. The human then starts `claude` in the project folder.
2. The lead session runs `./setup.sh` there ([Setup](#setup)); `CLAUDE.md` describes the first
   session.
3. All the work happens in the project folder: the brand files, the script, the score, the
   scenes, the captures, the edit and every render.

**A project is a copy.** Later kit updates do not reach existing projects. To take an update, run
the updated kit's `./install.sh <project-dir> --force`: it overwrites the engine files that have
the same name and deletes nothing. It leaves `BRAND.md`, `brand/` and `design.json` alone, since
the kit has no such files, and `.gitignore`, `music/CREDITS.md` and `broll/CREDITS.md`, which are copied only
when absent. It overwrites any engine file the project patched. Every such patch is recorded in
the project's `NOTES.md`; read it before the update and re-apply the patches after it. If a
`--force` install is interrupted, rerun the same command to finish it.

**Each project has its own environments and samples.** `setup.sh` creates the project's Python
environments and downloads its own sample libraries into `music/samples/` (about 3.4 GB download,
5 GB on disk). `./setup.sh --no-samples` skips them for a video without music or with a score of
synthesized instruments only.

## Requirements

- **A Linux machine or a Mac. A GPU makes renders fast but is not required.** Motion graphics and
  the edit render through OpenGL (3.3 for motion graphics, 4.1 for the edit). On Linux that is
  headless EGL with any driver: NVIDIA, AMD or Intel, or Mesa's llvmpipe, which renders on the CPU
  on a machine or VM without a GPU ([CPU-only machines](#cpu-only-machines)). The kit was tested
  on Linux with an NVIDIA GPU; there NVENC encodes previews and CUDA decodes sources, but only
  because a probe shows they work, and on any other machine ffmpeg encodes with libx264 and
  decodes on the CPU. On a Mac (Apple Silicon or Intel) it is the OpenGL 4.1 that macOS ships,
  with VideoToolbox for encoding and decoding; [Running on macOS](#running-on-macos) lists what
  differs.
- **About 25 GB of free disk**: 5 GB of sample libraries (plus 3.4 GB of archives while
  `setup.sh` unpacks them) and room for renders, which reached about 11 GB for a three-minute
  video. At the end of one project the folders held roughly: `music/` 9 GB (samples, stems,
  rejected scores), `motion/` 7 GB (ProRes alpha clips), `edit/` 3 GB, `broll/` 1 GB. Without
  the sample libraries (`./setup.sh --no-samples`) about 17 GB.
- **Optional: a Gemini API key with billing enabled**, only for a narrated voice (Gemini TTS),
  generated b-roll and the listening judge. The free tier allows only 10 TTS requests a day, which
  runs out during the first voice auditions. Without a key the lead reviews audio with ffmpeg
  measurements only ([The listening judge](#the-listening-judge)).
- **Claude Code**, with access to Opus. Fable helps where taste is the product (music, motion
  design); Sonnet does simple jobs.
- **Command-line tools**: `uv`, `ffmpeg` and `ffprobe` with the `libx264`, `prores_ks` and `aac`
  encoders, `curl`, `tar`, `unzip`, and on Linux `xz` (the macOS `tar` unpacks `.tar.xz` itself).
  The system fonts the renderers use for any role `design.json` leaves unnamed: on Linux DejaVu
  Sans and DejaVu Sans Mono (`fonts-dejavu-core`), on macOS Helvetica and Menlo,
  which ship with it. Optional: `rg` (ripgrep, used by the search commands below), `tmux` and the
  fallback fonts for terminal captures (on Linux DejaVu Sans Mono, Noto Sans Symbols and Symbols
  2, Noto Sans Math, Noto Color Emoji; on macOS Menlo, Apple Symbols and Apple Color Emoji, which
  ship with it), Chromium for web captures. `system-deps.sh` installs the system packages
  ([System packages](#system-packages)).
- **Your product**: its repository or docs, and for UI captures a build of its web frontend or its
  CLI.

## Setup

1. The human installs the kit into a new project folder for every video (see [Install into a
   project](#install-into-a-project)). That also runs `system-deps.sh`, the only step that needs
   administrator rights ([System packages](#system-packages)). The human then starts `claude`
   there. Steps 2-4 run in the project.

2. The lead sees what is missing, then fetches it. `setup.sh` needs no administrator rights:

   ```bash
   ./setup.sh --check        # report only; changes nothing
   ./setup.sh                # install and fetch everything missing
   ./setup.sh --no-samples   # the same, without the music sample libraries
   ```

   `setup.sh` never uses sudo and an agent never runs anything that needs it. A missing system
   package (a command, a font, Mesa) shows as MISSING or WARN with the hint to run
   `./system-deps.sh` in a terminal outside Claude Code, or to ask an administrator. It runs under the bash 3.2 that
   macOS ships. It checks the commands and ffmpeg encoders above (plus a test encode through the hardware H.264 encoder,
   `h264_nvenc` on Linux or `h264_videotoolbox` on macOS), runs `uv sync --frozen` in `edit/`,
   `motion/`, `music/`, `fixtures/web/` and `fixtures/tui/` (Python versions pinned), opens the
   edit's and the motion renderer's GL contexts and reports their renderer, checks fonts
   (`design.json` if the project has one, the system fonts, the terminal fallback fonts; see
   [Design system](#design-system)), checks the brand files ([Brand](#brand)), checks that
   every kit skill is in `.claude/skills/<name>/` in the project ("Claude Code skills"), downloads and unpacks the sample libraries into `music/samples/` (resumable; `--no-samples`
   skips them), installs Chromium through Playwright, fetches the Whisper model that
   `edit/words.py` names, and checks for the API key. It exits 1 while anything required is
   MISSING. Rerun it until the summary shows 0 MISSING. WARN lines are optional: the API key
   matters only for a narrated voice, generated b-roll and the listening judge, the sample
   libraries only for a score with sampled instruments (piano, strings, mallets, horn, orchestral
   percussion), the Whisper model only for narration word timings, `tmux` and the fallback fonts
   only for terminal captures, Chromium only for web captures, without the hardware encoder previews fall
   back to libx264, a software renderer (llvmpipe) renders on the CPU, much more slowly, and a
   project without `BRAND.md` renders in neutral defaults.

   The "Fonts" section prints one of each pair of lines (the `design.json` line has four forms):

   ```text
   ok        design.json            absent: system fonts and neutral colours in use
   ok        design.json            fonts and colours valid
   MISSING   design.json            <the loader's error: the key and the path, or the bad value>
   WARN      design.json            run ./setup.sh first to check it
   ok        system fonts           DejaVu Sans, DejaVu Sans Mono
   WARN      system fonts           DejaVu Sans not found (...): run ./system-deps.sh in a terminal outside Claude Code ...
   ok        fallback fonts
   ```

   When `design.json` names a font by family, a `font families` line comes first: `ok` with the
   number of roles resolved, `WARN` for a weight or style the family lacks, or `MISSING` with the
   family and where to put its files. `setup.sh` runs `tools/fonts.py` for it (only with
   `--check` under `./setup.sh --check`); see [Fonts by family](#fonts-by-family).

   On macOS the system fonts line reads `ok system fonts Helvetica, Menlo`. The "Brand" section
   after it prints:

   ```text
   ok        BRAND.md
   WARN      BRAND.md               optional: run the brand skill in Claude Code to create it
   WARN      design.json            older than <file>: rerun the brand skill
   ok        logo                   <path>
   MISSING   logo                   <error>
   WARN      logo                   run ./setup.sh first to check it
   ```

   The logo line appears only when `design.json` has a `logo` key. A bad logo path also shows as
   MISSING under "Fonts", because `design.json` is validated as a whole. The "Claude Code skills"
   section checks that every kit skill (`brand`, `narration`) is in `.claude/skills/`; a missing
   one gives `MISSING brand skill ... rerun install.sh from the kit`.

3. If the video uses a narrated voice, generated b-roll or the listening judge, the human puts
   the API key in their shell profile and restarts `claude` (`tts.py` also accepts
   `GOOGLE_API_KEY`). The key is never pasted into the chat:

   ```bash
   export GEMINI_API_KEY=<your key>   # https://aistudio.google.com/apikey
   ```

4. Claude Code settings. The lead session works with named teammates that message each other, a
   feature called agent teams that is off by default. Visual work uses the `frontend-design`
   plugin. `install.sh` writes both into the project's `.claude/settings.json`, so they apply in
   the project folder only and leave the human's other projects alone:

   ```json
   {
     "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" },
     "enabledPlugins": { "frontend-design@claude-plugins-official": true }
   }
   ```

   If the first session in the project does not offer to install the plugin, install it:

   ```bash
   claude plugin install frontend-design@claude-plugins-official
   ```

   If the plugin install says the marketplace is unknown, run
   `/plugin install frontend-design@claude-plugins-official` inside the session. The project's
   skills in `.claude/skills/` (`narration`, `brand`) are picked up automatically; in a session
   that was already running, run `/reload-skills`.

### Install into a project

```bash
./install.sh <project-dir> [--force] [--no-system] [--setup]
```

`install.sh` copies the kit into `<project-dir>` (created if missing; a relative path is fine, a
path inside the kit folder is refused):

- every top-level item of the kit except `install.sh`, `claude-skills/`, `claude-settings.json`
  and `mac_port_testing.md`, with executable bits
  and dotfiles such as `.python-version`; `.venv`, `__pycache__`, `.pytest_cache`,
  `.ruff_cache`, `.mypy_cache`, `out/`, `build/`, `.git` and `music/samples/` are left out;
- every skill under `claude-skills/` to `<project-dir>/.claude/skills/<name>/`, where Claude Code
  loads project skills: `narration` (Gemini TTS, [Narration](#narration)) and `brand` (`BRAND.md`
  to `design.json`, [Brand](#brand)); each skill folder must contain a `SKILL.md`. A new skill
  added to the kit also goes into `KIT_SKILLS` in `setup.sh`, the list it checks in a project;
- `CLAUDE.md` to `<project-dir>/CLAUDE.md`, the instructions every agent session in the project
  reads, and `HUMAN.md`, the human's guide, with the other top-level files;
- `claude-settings.json` to `<project-dir>/.claude/settings.json` (agent teams on, the
  `frontend-design` plugin enabled), only when the project has no settings file yet. An existing
  one is never overwritten, even with `--force`; if it lacks the agent-teams entry, the install
  says so and names the line to add.

If the project already holds a file the install would write, it lists them and exits 1 without
writing anything; `--force` overwrites those files and deletes nothing, except `.gitignore`, `music/CREDITS.md` and
`broll/CREDITS.md`, which are never overwritten. That is how a project
takes a kit update, and it overwrites engine files the project patched ([How the kit is
used](#how-the-kit-is-used)). After copying, the install runs the project's `./system-deps.sh`
in the human's terminal (it asks for the password itself); `--no-system` skips that for a
machine where the human has no administrator rights. `--setup` then runs
`./setup.sh` in the project and returns its exit code. It ends by printing the next
steps: `cd` into the project, start `claude`, and say you want to make a video; the lead runs
`./setup.sh` and asks the rest.

### System packages

```bash
./system-deps.sh [--yes] [--dry-run]
```

`system-deps.sh` is the only script that needs administrator rights, and a person runs it in their
own terminal, outside Claude Code: an agent never runs it, never runs sudo, and asks the human to
run it when `setup.sh --check` reports a MISSING system package. `install.sh` runs it after
copying; run it again at any time. It skips whatever is present, prints one list of what it will
install, and asks `Continue? [Y/n]` once (`--yes` skips the question; `--dry-run` prints the list
and changes nothing). It exits non-zero with a message on failure. It installs:

- **macOS**: Homebrew first if `brew` is missing (Homebrew's official installer, which asks for
  the password), then `ffmpeg`, `ripgrep` and `tmux`. `curl`, `tar`, `unzip` and the fonts ship
  with macOS.
- **Debian and Ubuntu** (`apt-get`): `ffmpeg`, `curl`, `tar`, `xz-utils`, `unzip`, `ripgrep`, `tmux`,
  Mesa's `libegl1`, `libegl-mesa0` and `libgl1-mesa-dri` (headless EGL and CPU rendering),
  `fonts-dejavu-core`, `fonts-noto-core`, `fonts-noto-color-emoji`, and Chromium's OS libraries
  through `uvx playwright@<version in fixtures/web/uv.lock> install-deps chromium`, which uses
  sudo itself and skips what is installed. It does not download the browser: `setup.sh` does.
- **Fedora** (`dnf`): the same tools and Mesa (`mesa-libEGL`, `mesa-dri-drivers`), the DejaVu and
  Noto Color Emoji fonts, and `ffmpeg` from the RPM Fusion free repository (Fedora's own build
  lacks `libx264`). Playwright's `install-deps` does not support Fedora, so Chromium's libraries
  are not installed there.
- **Any other Linux**: it prints the package list and exits 1.
- **Everywhere**: `uv`, with the official installer (no administrator rights) when missing, into
  `~/.local/bin`; a terminal opened before the install may need to be reopened to find it.

### What has been verified

On a Linux machine with an NVIDIA GPU, the kit was installed with `install.sh` into an empty folder
and set up there with `./setup.sh` from an empty home directory (the sample libraries were linked
in rather than downloaded). The run reported everything ready except the API key. With those
environments every self-test passed:

| Workstream  | Self-test (run from its folder)      | Output                                                                                                                                                                                                                                        |
| ----------- | ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| motion      | `uv run python render.py --selftest` | prints `GL_RENDERER`; `out/selftest_01.50.png`, `out/selftest_contact.png` and `out/selftest.mp4` (2 s, 120 frames at 1920x1080: a text card, a circle, a rounded square, a hairline, and the logo under the card if `design.json` names one) |
| edit        | `uv run bg_test.py [seconds]`        | `out/bg_test.mp4` (default 6 s at 1920x1080, 60 fps): the background and one browser-chrome window titled "edit self-test" around the placeholder `broll:selftest`                                                                            |
| music       | `uv run render.py --selftest`        | `out/selftest/soundtrack.wav` and stems, 17 s of synthesized C major at -16 LUFS                                                                                                                                                              |
| TUI capture | `uv run tuicap --selftest`           | `../../captures/tui-selftest/selftest.mp4`                                                                                                                                                                                                    |

Each self-test reads the project's `design.json` when there is one, so it also shows the
project's fonts and colours.

The motion and edit self-tests also passed with CPU rendering forced (Mesa llvmpipe; see
[CPU-only machines](#cpu-only-machines)), and the kit was run on a CPU-only Proxmox VM. Each engine was also driven through its project
interface with throwaway project files that are not part of the kit: a short arrangement on the
sampled instruments, two scenes rendered by `render_all.sh`, a narration timeline from test tones, a
timeline without narration (sections timed by `duration` and by on-screen `text`, and one mixed
with a narrated section), an EDL with placeholder shots and a credit line (frames, preview, mix,
credits; also with no narration, music or b-roll, which gave a preview with a silent audio
track), a web clip captured from a one-page frontend, and CLI and tmux clips. The
narration skill, the listening judge and the b-roll generator were not run: they need an API key.

The macOS support was written from the documentation and source of moderngl, glcontext, skia and
ffmpeg and checked on Linux (the scripts under bash 3.2, the macOS branches of `setup.sh` with
`uname` faked, the music render with macOS's process start method), but has not yet run on a Mac.
On a Mac, start with `./setup.sh --check`, then the self-tests above; `mac_port_testing.md` is
the full checklist.

### Running on macOS

- **macOS version**: Apple Silicon needs macOS 14 or later (the `av` package that
  `faster-whisper` pulls into `edit/` has no older wheel); on Intel Macs the Python packages
  install from macOS 12. There `edit/` installs `onnxruntime` 1.23.2, the last release with Intel
  Mac wheels; every other platform keeps the locked 1.30.0.
- **Prerequisites**: Homebrew and `brew install ffmpeg` (its build includes `libx264` and
  VideoToolbox), optionally `ripgrep` and `tmux`; `system-deps.sh` does all of it. `xz` and
  fontconfig are not needed.
- **GPU**: macOS has no EGL. moderngl opens a CGL context instead, which offers OpenGL 4.1 core
  (deprecated by Apple but still shipped; on Apple Silicon it runs on Metal), and the edit's
  shaders are written for 4.1. skia finds the context through its native interface
  (`GrDirectContext.MakeGL()` with no argument). The OS-specific choices for the edit live in
  `edit/editkit/hw.py`; motion graphics choose in `motion/lib/gfx.py`.
- **Speed**: there is no NVENC or CUDA. `--preview`, `--fast` and placeholder clips encode with
  `h264_videotoolbox` at 20 Mb/s, and sources decode through VideoToolbox, scaled on the CPU
  (`flags=area`) where Linux with CUDA scales on the GPU (lanczos), so a Mac preview differs from
  such a Linux one in fine detail. Expect GPU renders and encodes to take longer than on a Linux
  machine with an NVIDIA GPU (Whisper runs on the CPU on both systems). Full masters use libx264
  on both systems. When ffmpeg lacks the hardware encoder, previews fall back to
  `libx264 -preset veryfast` and `setup.sh` warns.
- **Music**: worker processes start fresh on macOS (Python's `spawn`) and load the instrument
  tables again, which adds a few seconds to a render.
- **Terminal captures**: the fallback fonts are Menlo, Apple Symbols and Apple Color Emoji from
  `/System/Library/Fonts/`; a missing one is skipped, and a glyph no font has is drawn as the mono
  font's empty box. Where `design.json` names no font, the renderers use Helvetica and Menlo from
  the same folder. The captured programs run with `LANG=en_US.UTF-8`, since macOS may lack
  `C.UTF-8`. macOS has no `/proc`: a capture that reads process details there must use `ps`.
- **Web captures**: Playwright's Chromium needs nothing else on macOS; `playwright install-deps`
  is for Linux only.
- **Listening to a take**: `afplay out.wav` instead of `aplay`.

### CPU-only machines

The kit runs on a Linux machine or VM without a GPU, more slowly; it was tested on a Proxmox VM
with no GPU:

- **Rendering**: headless EGL falls back to Mesa's llvmpipe when no GPU driver is present. If the
  context does not open, Mesa is missing (`libegl1`, `libegl-mesa0`, `libgl1-mesa-dri`): the human runs
  `./system-deps.sh`.
  `setup.sh` reports the two GPU lines as WARN ("CPU rendering: much slower") rather than MISSING.
- **Encoding and decoding**: previews and placeholders encode with `libx264 -preset veryfast`, and
  sources decode and scale on the CPU. `edit/editkit/hw.py` probes NVENC and CUDA once per process
  with a short test encode and decode, so an ffmpeg build that lists `h264_nvenc` without an
  NVIDIA driver is handled.
- **Speed**: CPU rendering is many times slower than a GPU, and how much slower depends on the
  machine's core count. Time the self-tests on your machine to know what to expect, and review
  with `--preview` and `--range` rather than full-quality renders.
- **Forcing CPU rendering** on a machine with a GPU (to compare, or around a driver problem): set
  `LIBGL_ALWAYS_SOFTWARE=1`. With the NVIDIA driver installed, also set
  `__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json`, or NVIDIA's EGL
  answers instead of Mesa. glcontext's `GLCONTEXT_DEVICE_INDEX=<n>` picks one of several EGL
  devices. Only an NVIDIA machine was tested this way; with an AMD or Intel driver Mesa may refuse
  `LIBGL_ALWAYS_SOFTWARE` for a context opened on a hardware device, and the device index is the
  way to reach llvmpipe.

## The team

One **lead** session talks to the human, owns the script and the timeline, briefs the specialists,
reviews every output, and decides. The specialists are agent-team teammates
(agent teams are on in `.claude/settings.json`), each with a name (so the lead and the others can message it) and exclusive ownership
of its folders:

| Role                | Tier                                                   | Owns                                                                                                             | Job                                                                 |
| ------------------- | ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| lead (main session) | Opus                                                   | `narration/`, `tools/`, `NOTES.md`, `HANDBOOK.md`, `BRAND.md`, `brand/`, `design.json` (through the brand skill) | script, narration, timeline, shared spec, briefs, review, decisions |
| composer            | Fable (an Opus composer had two scores rejected first) | `music/`                                                                                                         | composition and rendering                                           |
| motion designer     | Fable                                                  | `motion/`, minus any scene handed to a second designer                                                           | motion-graphics scenes                                              |
| scene designer      | Fable                                                  | one scene file and its outputs                                                                                   | a scene the human asked to have rebuilt from scratch                |
| web capture         | Opus                                                   | `fixtures/web/`, `captures/web/`                                                                                 | mock server and browser capture of the web UI                       |
| TUI capture         | Opus                                                   | `fixtures/tui/`, `captures/tui/`                                                                                 | terminal and CLI captures                                           |
| b-roll              | Sonnet (or the lead)                                   | `broll/`                                                                                                         | generating shots, contact sheets, normalising picks                 |
| editor              | Opus                                                   | `edit/`                                                                                                          | compositor, edit decision list, mix, subtitles, credits, masters    |

Only the workstreams the human chose exist: the composer only with music, b-roll only with
b-roll, and the lead's narration work (script recording, takes, the judge) only with narration.
Without narration the lead still owns `narration/`, because it holds the timeline.

Pick the tier per job: Sonnet for a search-and-cut task, Opus for engineering-heavy capture and
editing, Fable where taste is the product (motion design, music) or where an attempt at the same
thing already failed. Escalate one tier only after a failed attempt, and hand the stronger agent
the task, both attempts and their evidence. Later work on the same piece (extending a score after
a new section) goes to the tier that succeeded.

### Rules that make the team work

1. **One owner per file.** Two agents writing the same file lose work. Agents may import another's
   library but never modify it; a second designer brought in for one scene gets exactly that
   scene's file and its outputs.
2. **Files plus short messages.** Each workstream writes its outputs and a `manifest.json`;
   messages say what changed and where. The editor never needs to ask when a dialog opens; it
   reads the mark.
3. **The timeline is the only clock.** Every agent reads `narration/timeline.json`, never a number
   from a message. When it changes, send absolute windows, not deltas.
4. **Human decisions are written down first.** Every decision and correction goes into `NOTES.md`
   before anyone is briefed; every agent treats that file as binding. Then the lead tells the
   affected agents, with exact times, file or symbol references and acceptance checks.
5. **The lead reviews before the human sees anything** (see [Review and QA](#review-and-qa)), and
   purges rejected elements from every agent's work: an edit decision list can still reference a
   rejected animation after the motion designer has dropped it.
6. **Previews before masters.** The editor renders `--preview` or `--range` for review and the full
   master only after the lead's OK. Hold the master while any upstream asset is being re-rendered.
7. **Messages cross.** An agent's report covers the brief it finished; newer messages may still be
   queued. Check whether the agent is running or idle and look at file timestamps before
   re-sending or re-spawning.
8. **Wait on files or explicit messages.** A watcher loop that searches for another agent's
   process (`pgrep` on its command line) can match its own command line and never end.
9. **Change only what was asked.** When the human asks to replace one beat, leave the rest of the
   scene and the cut unchanged and re-render. A scene redesign keeps its story beats and its
   narration sync.
10. **Hands off the product.** No writes to the product's repository (it is the read-only source of
    truth for facts and its docs; logo and font files are copied into `brand/`), no system installs, never `pip install`
    (use `uv`), no git inside the video project unless you want it.
11. Visual work uses the `frontend-design:frontend-design` skill for guidance.

### Good briefs

- the goal and the reference points: the agent's part of the HANDBOOK "Brand" section, plus the
  human's own references, with what each one means to the human;
- what the agent owns and what it must never touch;
- exact deliverables: file names, sizes, codecs, a manifest with named marks;
- how to check its own work without eyes or ears (contact sheets, spectrograms, the judge);
- a final report format: paths, commands to re-render, known weaknesses.

During long renders a recurring five-minute status check (a scheduled prompt) keeps the human
informed; cancel it when the work settles.

## The workflow

### Phase 0: kickoff

The first session in a blank project runs the kickoff in the order `CLAUDE.md` gives under "First
session": setup, the interview, the key, the brand, `NOTES.md`. This phase lists what each step
is for.

1. **Learn the product from its own documentation.** Read the repository's docs or its docs index
   and pull only the sections the video needs (the features it will mention). Accurate claims in
   the script depend on this, and so do the fixtures later.
2. **Check the machine.** `./setup.sh --check`.
3. **Run the brand skill** ([Brand](#brand)). Without `BRAND.md` it interviews the human and
   writes it; with it, it generates `design.json` and writes the "Brand" section of
   `HANDBOOK.md`, one part per workstream. That section feeds the shared spec in Phase 2. Put the
   skill's questions about gaps and conflicts to the human with the questions below.
4. **Confirm the scope**: which of narration, music and b-roll the video has (the kickoff
   interview in `CLAUDE.md` asks). The others are out of scope: no workstream, no brief, no questions about them.
5. **Ask only the questions whose answers change the plan.** Typically: how to make the music
   (compose with real samples, or a local AI model with a non-commercial licence) if there is
   music, the output format (1080p60), and the narrator's character if there is narration. Decide
   everything else and report it.

### Phase 1: the timeline first

Every workstream is timed to `narration/timeline.json`, so it comes first. Write the script as
short sections, one per scene.

- **With narration** the voice is the clock: audition voices, calibrate the energy with the human,
  record two or three takes per line, judge them against the text, process the chosen takes
  uniformly, and build the timeline.
- **Without narration** the lead writes `sections.json` with each section's on-screen text
  (titles, captions, card text) and, where the script or storyboard fixes one, a `duration`. The
  timeline estimates the other sections' lengths from the reading time of their text and marks
  them `~est`; the human approves the pacing, and tunes it at review with `duration`.

A video can mix both, section by section. Details in [Narration](#narration).

### Phase 2: the shared spec and the briefs

The lead writes a shared spec (the design system from `design.json` and the HANDBOOK "Brand"
section, the fixture story every capture must tell, scene list, deliverable conventions, manifest
marks) and spawns the agents for the chosen workstreams in one message, each with a complete
brief that points to
`BRAND.md` and its part of the "Brand" section.

**The fixture story.** Every capture shows the same imaginary project, account or dataset, so the
web UI, the terminal UI and the motion graphics agree. Write it down once in the shared spec, as
data: the things the product shows (ids, names, states), every relationship between them, and the
arc over time (what is true at the start, what changes in which order, how it ends, and how many
on-screen seconds each change takes). The web mock, the TUI fixtures and every scene that shows
the story copy it from that one table. A table of this shape works:

| #   | Id     | Kind     | Shown as                            | Related to | Changes during the clip                   |
| --- | ------ | -------- | ----------------------------------- | ---------- | ----------------------------------------- |
| 1   | `<id>` | `<kind>` | `<label as the product renders it>` | none       | `<state>` at the start                    |
| 2   | `<id>` | `<kind>` | `<label>`                           | 1          | `<state> -> <state>` at clip second `<t>` |

- If the story holds a graph, it has no redundant (transitively implied) edges. A reviewer will
  spot one in the rendered graph; check the data before capturing, because a fix afterwards costs
  a re-capture and several re-renders.
- One notation for the same data across fixtures (a column of names, a unit). If two fixtures
  already render a row differently, both can stay, but new work follows one of them. The same
  goes for version strings such as a tool's banner: keep them equal everywhere, and re-capture
  only the clips where a stale value is visible.
- Keep the mood calm: things work, change and finish; no alarms unless the narration is about
  one.
- Show only what the real product renders, and name things as the product names them.

### Phase 3: production

Every workstream runs in parallel from the spec and the timeline. Techniques, commands and
lessons per workstream are in [Workstream guides](#workstream-guides).

### Phase 4: the review loop

The lead reviews every output without watching it, through contact sheets, stills, crops and
measurements ([Review and QA](#review-and-qa)), then points the human at a preview.

The human sends short, direct notes. Most are about taste (energy, colour, motion) or about facts
in the script. Typical ones and what they turn into:

| Kind of note                                                               | What it turns into                                                                                                                                                                                           |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| The score is rejected                                                      | Rewrite the composer's brief with what was rejected and why. If the second score is also rejected, give the job to a stronger model with both failures as evidence                                           |
| The logo animation is disliked                                             | Offer three alternatives as one-line options with ASCII previews; record the rejected one in `NOTES.md` ([Rejected styles](#rejected-styles)); the chosen one can become the visual motif of the whole piece |
| A product term is wrong (a component called by the name of something else) | Correct the script, the scene and every label; record the rule in `NOTES.md`                                                                                                                                 |
| A diagram of the product's data is wrong                                   | Fix the fixture story and every web clip, TUI clip and motion scene that shows it; put the lesson in the shared spec                                                                                         |
| The look is wrong (too dark, wrong colour, wrong type)                     | Change `BRAND.md` with the human, rerun the brand skill, then delete `edit/build/placeholders/` and re-render stills of the affected scenes for the human to compare                                         |
| The human asks the lead to stop asking and decide                          | From then on the lead decides and reports, asking nothing                                                                                                                                                    |
| A defect on the logo in the first frame                                    | Trace it by comparing the source frame with the master; fix it at the source, never by repairing the frame downstream                                                                                        |

**Propagating a change.** When the script changes, the order is always the same: record the
decision in `NOTES.md`, re-record the line (two or three takes, judged; without narration, update
the section's `text` or `duration`), rebuild `timeline.json`, then message the composer (re-grid),
the motion designer (new windows, absolute times) and the editor (re-anchor on words), each only
if the video has that workstream. The editor holds the master until every upstream re-render has
finished. Inserting a new section shifts everything after it by its length; give every
downstream agent the new absolute windows.

### Phase 5: finishing

- **The first frame.** Many sites show the first frame as the thumbnail, so frame 0 is a designed
  image, never black: for example the logo alone on the project background, a motion scene's
  still drawn with `logo.draw` ([The logo in a scene](#the-logo-in-a-scene)) and held by the edit
  as `still:<path>`.
- **Credits** generated from the files that record licences, so the on-screen credits and the
  video description cannot disagree ([Subtitles and credits](#subtitles-and-credits)).
- **The ending.** A measured fade to pure black: grain and dither have to fade with the picture, or
  the black frames stay gray.
- **Subtitles.** An SRT built from the script text and the whisper word times; none without
  narration.
- **A render guard.** The editor's full render refuses to run while any shot would use a
  placeholder.
- **Encodes**: the master, then the share copy ([Encoding](#encoding)).

### A reusable plan

1. Read the product's docs; list the features and the claims you'll make; verify each claim.
2. Run the brand skill: `BRAND.md` and `brand/` in, `design.json` and the HANDBOOK "Brand"
   section out.
3. Confirm which of narration, music and b-roll the video has. Ask the human the two or three
   questions that change the plan (music approach, format, voice), plus the brand skill's open
   questions.
4. Write the script as short sections. With narration: audition voices, calibrate energy, record
   takes, judge them. Without: give each section its on-screen text or a duration.
5. Build `timeline.json`. From here on it is the only clock.
6. Write a shared spec: design system, fixture story, deliverable conventions, manifest marks.
7. Spawn one agent per workstream, each with exclusive ownership and a complete brief.
8. Let the lead review every output with contact sheets, stills, crops and measurements.
9. Show the human a preview; record every note in `NOTES.md`; propagate changes in a fixed order.
10. Finish: a designed first frame, credits from data, subtitles, loudness, a measured fade, a
    render guard.
11. Keep `HANDBOOK.md` current so the next agent can pick the project up cold.

## Pipeline and folder map

```text
BRAND.md + brand/ ──brand skill──> design.json (fonts, colours, grain, logo; read by motion, edit, tuicap) + HANDBOOK.md "Brand" (every brief)
narration/NN_*.txt ──narration skill (Gemini TTS)──> narration/vN/*.wav ──process.sh (sources.json)──> narration/final/*.wav
                                                 └─build_timeline.py (sections.json)──> narration/timeline.json  (THE clock)
timeline.json ──> music/arrangement.py ──music/render.py──> music/out/soundtrack.wav + stems + manifest.json (bar grid)
timeline.json ──> motion/scenes/*.py ──motion/render.py──> motion/out/<scene>.mp4 / *_alpha.mov + manifest.json (marks)
fixtures/web/product.py (mock server, clips) ──webcap (Playwright)──> captures/web/*.mp4 + manifest.json (marks, cursor tracks)
fixtures/tui/product.py (the product's CLI in a pty) ──tuicap (pyte + skia)──> captures/tui/*.mp4 + manifest.json
broll/gen/shots.json ──tools/genvideo.py (Gemini Omni)──> broll/gen/omni/*.mp4 ──> broll/candidates/NN_*.mp4
all of the above ──> edit/words.py (whisper word times) ──> edit/edl.py (edit decision list)
                ──> edit/mix.py (mix.wav) ──> edit/render.py (GPU compositor) ──> edit/out/intro.mp4
                ──> edit/subs.py (SRT), edit/credits.py (CREDITS.txt)
```

**Rebuild order after a change**: brand (after `BRAND.md` or `brand/` changes: the brand skill,
then every renderer that shows the change), narration, timeline, music (if timing moved), motion (if a scene
window or its content changed), captures (only if the fixture story changed), edit.

Each workstream is a folder with its own `uv` project (`pyproject.toml`, `uv.lock`,
`.python-version`). Run every command from inside its folder with `uv run ...`. `tools/*.py`,
`narration/build_timeline.py` and the narration skill's `tts.py` are single-file `uv` scripts that
declare their own dependencies. Scripts find each other by relative path (`edit/` reads
`../narration/timeline.json`, `music/` reads `samples/`), so keep the folder layout as it is.

### Engine and project files

The engine column ships with the kit and works for any product as it is. The project column is
what the team writes; each entry point that needs a project file stops with a message naming the
file and the README section that describes it.

| Folder                   | Engine (in the kit)                                                                                                                                                                                                                                           | Files the project writes                                                                                                                                                                                                                                                                               |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| project root             | none                                                                                                                                                                                                                                                          | `BRAND.md` (brand guidelines, the source of truth for look, voice and sound), `brand/` (`logo/`, `fonts/`, `palette/`, `reference/`), `design.json` (generated by the brand skill) ([Brand](#brand), [Design system](#design-system)); `NOTES.md`, `HANDBOOK.md` ([Project records](#project-records)) |
| `tools/`                 | `listen.py` (Gemini listens to or watches media and answers questions), `genvideo.py` (Gemini Omni b-roll), `fonts.py` (finds the files for fonts that `design.json` names by family)                                                                         | none                                                                                                                                                                                                                                                                                                   |
| `claude-skills/`         | `narration/` (Gemini TTS: `SKILL.md`, `tts.py`), `brand/` (`BRAND.md` to `design.json`: `SKILL.md`, `BRAND.template.md`, `check.py`); `install.sh` and `setup.sh` copy each to `.claude/skills/<name>/`                                                       | none                                                                                                                                                                                                                                                                                                   |
| `install.sh`, `setup.sh` | copy the kit into a project; install and check dependencies                                                                                                                                                                                                   | none                                                                                                                                                                                                                                                                                                   |
| `CLAUDE.md`              | project instructions every agent session loads; `install.sh` puts it in the project root                                                                                                                                                                      | none                                                                                                                                                                                                                                                                                                   |
| `narration/`             | `process.sh` (trim ends, cap pauses at 0.45 s, tempo +4 %), `build_timeline.py`                                                                                                                                                                               | `NN_name.txt` scripts, `sections.json` (order, delivery, timing), `sources.json` (chosen takes); generated: `vN/`, `final/`, `timeline.json` ([Narration](#narration))                                                                                                                                 |
| `music/`                 | `scorekit/` (`library`, `sampler`, `synth`, `instruments`, `percussion`, `drums`, `parts`, `theory`, `score`, `timing`, `mix`, `qc`), `render.py` with `--selftest`; `CREDITS.md` lists the sample libraries                                                  | `arrangement.py`: `compose(seed) -> Score` ([Music](#music))                                                                                                                                                                                                                                           |
| `motion/`                | `lib/` (`gfx`, `design`, `logo`, `ease`, `encode`, `scene`, `ui`, `selftest`), `render.py` with `--selftest`, `render_all.sh`                                                                                                                                 | `scenes/<name>.py` (one per scene, defining `SCENE`), `scenes.txt` (what `render_all.sh` renders) ([Motion graphics](#motion-graphics))                                                                                                                                                                |
| `fixtures/web/`          | `webcap/`: `director` (deterministic frame stepping), `browser`, `capture`, `probe`, `verify`, `world` (scripted clock), `server` (serving helpers, live preview), `agent_session` (a scripted coding-agent terminal), `ansi`, `project` (loads `product.py`) | `product.py`: `World`, `build_app`, `CLIPS`, plus your fixture data ([Web capture](#web-capture))                                                                                                                                                                                                      |
| `fixtures/tui/`          | `src/tuicap/`: `render` (pyte + skia terminal renderer), `design`, `glyphs`, `palette`, `capture` (pty recording, synthetic CLI shots), `tmux_clip` (isolated tmux), `clips` (the `tuicap` command, `--selftest`)                                             | `product.py`: `CLIPS`, optional `prepare`, `STILL_T`, `TRUECOLOR`, plus fixture files ([TUI capture](#tui-capture))                                                                                                                                                                                    |
| `edit/`                  | `editkit/` (`compositor`, `gpu`, `hw`, `decode`, `scene`, `ease`, `shaders/`, `cards`, `art`, `design`, `assets`, `shots`, `credit_data`, `project`); `render.py`, `mix.py`, `words.py`, `subs.py`, `credits.py`, `bg_test.py` (the self-test)                | `edl.py`: `END`, `build()`, optional `BROLL_CLIPS`, `BUSY`; optional `credits.json` ([The edit](#the-edit))                                                                                                                                                                                            |
| `broll/`                 | `CREDITS.md` (the format for CC BY clips)                                                                                                                                                                                                                     | `gen/shots.json` (prompts), a `CREDITS.md` section per CC BY clip ([B-roll](#b-roll))                                                                                                                                                                                                                  |

Folders the project creates as it goes: `narration/vN/` and `narration/final/`, `captures/web/`,
`captures/tui/` (clips, stills, manifests), `broll/gen/omni/` and `broll/candidates/`, every
workstream's `out/`, and `edit/build/` (`words.json`, art, single frames, cached placeholders).

**Not included**: brand files, a script, a score, scenes, capture code, an edit decision list,
prompts, and any recorded or rendered media. Until they exist, the edit shows a missing asset as a placeholder
in previews (`edit/render.py --allow-placeholders`). `setup.sh` fetches the sample libraries and
the Whisper model.

**Fonts and colours** come from the project's `design.json`, through one loader per renderer
(`motion/lib/design.py`, `edit/editkit/design.py`, `fixtures/tui/src/tuicap/design.py`); a font
is a path relative to the project root or a family name ([Fonts by family](#fonts-by-family)),
and nothing is installed system-wide. Without it
the renderers use the system fonts and neutral colours ([Design system](#design-system)).

## Code that needs your product

Only the two capture harnesses talk to the product. Each loads one project module, `product.py`
in its folder, and keeps the rest (frame stepping, pty recording, terminal rendering, manifests)
as engine. `product.py` reads where the product lives from environment variables, never from
hard-coded paths. Use these names, so every agent and `HANDBOOK.md` agree:

| Variable           | Meaning                                       | Typical use in `product.py`                             |
| ------------------ | --------------------------------------------- | ------------------------------------------------------- |
| `PRODUCT_REPO`     | the product's repository checkout (read-only) | CLI clips that run inside it; fixture data read from it |
| `PRODUCT_WEB_DIST` | the product's built web frontend              | `serve_dist(app, ...)` in the mock server               |
| `PRODUCT_BIN`      | the product's CLI binary                      | the commands TUI clips run                              |

`webcap.server.require_env(name, what)` returns the path or stops with a message saying what to
set. Two rules hold for any product:

- Run the product read-only against its repository. Build fixture state (a workspace, a scratch
  `HOME` with config) inside `fixtures/` with the product's own init commands, never by
  hand-editing its files.
- Keep the operator's own settings out of captures: `tuicap.capture.clean_env(home, drop=(...))`
  removes the product's environment variables (pass its prefix, for example `"<PRODUCT>_"`) and
  points `HOME` at the scratch home.

Narration, music, motion graphics and the edit run without the product.

## Deliverable conventions

- **Target format**: see [Encoding](#encoding). Output names carry no version suffix: master
  `edit/out/intro.mp4`, share copy `edit/out/intro-share.mp4`; each re-render replaces them.
- **Intermediates**: H.264 `-crf 10 -preset slow -pix_fmt yuv420p`, or ProRes 4444
  (`yuva444p10le`) when alpha is needed; constant 60 fps. Captures at 3840x2160 so pushes stay
  sharp; motion graphics at 1920x1080, rendered supersampled.
- **Manifests**: every workstream writes a `manifest.json` next to its outputs: file, size, fps,
  duration and timed marks (`{t, event}`; the web manifest adds `key_marks` and per-frame cursor
  tracks; the music manifest holds the bar grid). The edit places shots by these mark names, never
  by hard-coded times.
- **Files**: stills are lossless PNG. Write outputs to a temporary name and rename atomically, so a
  reader never sees a half-written file, and say "final" explicitly in the message.

`narration/timeline.json`, which every agent reads:

```json
{
  "total": 150.0,
  "narration": [
    {
      "name": "01_open",
      "file": "narration/final/01_open.wav",
      "start": 2.5,
      "end": 18.4
    },
    {
      "name": "01b_intro",
      "file": "narration/final/01b_intro.wav",
      "start": 20.5,
      "end": 22.1,
      "insert": true
    }
  ],
  "scenes": [
    { "scene": 1, "key": "open", "start": 0.0 },
    { "scene": 2, "key": "pitch", "start": 23.5 }
  ]
}
```

In a video without narration `narration` is an empty list; `total` and `scenes` are always
there.

A manifest entry the edit syncs to:

```json
{
  "file": "w2_settings.mp4",
  "duration": 18.85,
  "fps": 60,
  "key_marks": {
    "dialog opens": 1.817,
    "field focused": 3.417,
    "value typed": 10.4,
    "saved": 14.35
  }
}
```

## Workstream guides

### Narration

Owner: the lead. Folder: `narration/`.

The folder holds the video's clock, `timeline.json`, with or without a voice. A video without
narration needs only `sections.json` and `build_timeline.py` from this guide: skip to
[`sections.json`](#sectionsjson) and [A section without a take](#a-section-without-a-take).

**The `narration` skill** (`claude-skills/narration/`, installed by `setup.sh` to
`.claude/skills/narration/` in the project) turns a script into a 24 kHz mono WAV with
`gemini-3.8-flash-tts`.
Claude Code loads it whenever narration or text-to-speech is asked for; `SKILL.md` is the full
reference. The essentials:

```bash
SKILL=.claude/skills/narration   # from the project root
uv run $SKILL/tts.py script.txt --voice Charon --style "calm and warm" -o intro.wav
echo "Hello there." | uv run $SKILL/tts.py - -o hello.wav
uv run $SKILL/tts.py --list-voices
```

- Flags: `--voice` (prebuilt name or a `voicekey_...` id; default `Kore`), `--style` (one
  sustained delivery direction for the file), `-o`, `--model`. One narrator per file.
- Age, gender and accent come from the voice choice, never from `--style`. `SKILL.md` lists 30
  voices with their traits; for explainers try `Charon`, `Sadaltager`, `Iapetus`, for product
  demos `Puck`, `Achird`.
- The script is a verbatim transcript: every word in it is spoken, so directions go in `--style`.
  Pacing comes from punctuation plus `<short pause>` and `<long pause>` tags; momentary sounds
  (`<breath>`, `<laugh>`) are inline tags; spell out anything that might be read wrong (years,
  abbreviations), and drop markdown, URLs and code.
- Long scripts that stop early or drift: split at paragraphs, narrate each part with the same
  voice and style, join with `sox`.
- If you edit `tts.py`, keep the API client in a local variable (`client = genai.Client()`): a
  temporary client object is garbage-collected mid-request.

**Start from the brand.** The narrator's character, the vocabulary and the delivery come from
`BRAND.md`, "Voice and tone", and the narration part of the HANDBOOK "Brand" section. Audition
voices that fit it, and write style directions in its words.

**Write short sections**, one per idea, each in its own `narration/NN_name.txt` (`01_open.txt`,
`02_pitch.txt`, ...). Separate files let each section carry its own delivery direction and be
re-recorded alone. `edit/subs.py` reads these files for the subtitles, so they hold exactly what
is spoken. Delete or mark stale leftover scripts.

**Audition voices** on the same two lines: render 3-4 voices and let the human choose. The lead
cannot hear, so it asks the [listening judge](#the-listening-judge) about each take (perceived
age, warmth, pacing, artifacts) and to catch misreads.

**Calibrate the energy** with the human, and expect to overshoot both ways. "Warm and
contemplative, speaking slowly" reads as bored; "energetic, speaking with conviction" as too
eager; "warm and engaged, natural conversational pace, quietly confident" lands in the middle.
Never use "hushed", whispering, breathy or overly dramatic directions, or "slowly" or
"contemplative" as the whole style. Keep a full, clear speaking voice. Per-section changes stay
small (`, firm`, `, reflective`, `, lightly wry`, `, relaxed`, `, hopeful`,
`, a touch of gravitas`). Give the judge a target (energy 5-6 of 10).

**Record and judge takes.** The TTS model occasionally speaks stage directions (`<short pause>`
read aloud), drops a word, or adds vocal fry. Render two or three takes per changed line into a
new `vN/` folder and have the judge list word differences and pick one:

```bash
cd narration
uv run ../.claude/skills/narration/tts.py NN_name.txt --voice <Voice> \
  --style "warm and engaged, natural conversational pace, quietly confident" -o vN/NN_name_a.wav
uv run ../tools/listen.py --model gemini-3.5-flash \
  "Expected text: ... For each file: word differences, stage directions read aloud, mispronunciations, energy 1-10 (target 5-6). Final line: PICK <a|b>" vN/NN_name_a.wav vN/NN_name_b.wav
```

Budget TTS calls: batch auditions, and enable billing before you start.

**Install the chosen take.** Point `sources.json` at it, then process every take the same way and
rebuild the timeline:

```json
{
  "01_open": "v3/01_open_b.wav",
  "02_pitch": ["v2/02_pitch_a.wav", "v4/02_pitch_tail_a.wav"]
}
```

A list of two files joins them with 0.5 s of silence. Without `sources.json` (no narrated
section) `process.sh` has nothing to process and says so.

```bash
./process.sh               # trims ends, caps pauses at 0.45 s, atempo 1.04, 48 kHz -> final/*.wav
uv run build_timeline.py   # rewrites timeline.json and prints the scene table
```

#### `sections.json`

It holds the order, the delivery and the timing of the sections:

```json
{
  "first_start": 2.5,
  "tail": 3.8,
  "sections": [
    {
      "name": "01_open",
      "style": "warm and engaged, natural conversational pace, quietly confident"
    },
    {
      "name": "02_pitch",
      "style": "warm and confident",
      "gap": 2.0,
      "pin": 24.0,
      "scene_start": 23.5
    },
    { "name": "03_how", "style": "warm and engaged", "gap": 0.5 },
    { "name": "04_demo", "duration": 12.0 },
    { "name": "05_close", "text": "<tagline> <url>" },
    { "name": "01b_name", "style": "warm and confident", "insert": 20.5 }
  ]
}
```

| Field         | Meaning                                                                                     |
| ------------- | ------------------------------------------------------------------------------------------- |
| `name`        | the section: `NN_name.txt` holds its words, `final/NN_name.wav` its processed take          |
| `style`       | the `--style` direction its takes were recorded with (a record for re-takes)                |
| `gap`         | seconds of silence before it (default 0.5; ignored for the first section)                   |
| `pin`         | a fixed section start, so a re-take earlier in the order shifts nothing after it            |
| `scene_start` | a fixed scene start (default: the midpoint of the gap before its narration)                 |
| `key`         | the scene key the other workstreams use (default: the name after its number, `open`)        |
| `insert`      | a fixed start inside another scene's window; it adds no scene and shifts nothing            |
| `duration`    | seconds a section without a take lasts; it is silent (no narration entry)                   |
| `text`        | the words shown on screen; without a take or `duration`, their reading time sets the length |

Three optional top-level keys tune the reading-time estimate: `reading_cps` (default 15
characters per second), `min_hold` (2.5 s) and `pad` (1.0 s). The default suits languages written
with spaces, such as English; for Chinese, Japanese or Korean on-screen text, set `reading_cps`
lower (around 5) at the top level of `sections.json`.

**Timing model** (`build_timeline.py`): sections without `insert` play in list order, the first at
`first_start`, each later one after its `gap`; each starts a scene. Inserted lines sit where
`insert` puts them (a product name spoken during the logo reveal). A
silent window for a logo reveal is a long `gap` before the section after it, with `scene_start`
pinning where that scene begins. The picture total is the last section's end plus `tail`; the
editor appends the credits.

#### A section without a take

A section's length comes from the first of these that it has:

1. its processed take, `final/<name>.wav`: a narrated section, with an entry in `narration`;
2. `duration`: a silent section of that length;
3. `text`: a silent section lasting the text's reading time,
   `max(min_hold, len(text) / reading_cps + pad)`;
4. none of them: `build_timeline.py` stops and names the section and the three options.

A take in `final/` wins even over `duration`: delete a stale take to make its section silent.

A silent section starts a scene like any other but has no entry in `narration`, so it gets no
voice in the mix, no word timings and no subtitles. In a video without narration every section is
silent, `narration` is empty and `sources.json` is absent. The lead writes each section's
on-screen text (titles, captions, card text) into `sections.json`; the timeline estimates the
pacing from it, and the printed table marks those sections `~est`:

```text
 1 scene@   0.0  01_open             0.5 -     3.0  (2.50s) silent ~est (from text: confirm at review)
 2 scene@  3.25  02_pitch            3.5 -     6.7  (3.20s)
 3 scene@  6.95  03_demo             7.2 -    11.2  (4.00s) silent
```

The human confirms the pacing at review; a section whose estimate is wrong gets a `duration`,
which wins over `text`. Motion scenes can read the same `text`, so the on-screen words and their
timing come from one place.

- **Re-takes**: use one take whole. Splicing a new sentence into an approved take is audible
  (voice colour and room tone change at both joins).
- **Trims without re-recording**: find pauses with `silencedetect` and cut the source take with
  `atrim` and a short `afade` ([Snippets](#snippets)).
- **Wording changes of equal length** keep the timeline. Longer ones shift everything after them,
  so send downstream agents absolute windows.

### The listening judge

The judge is optional: it needs `GEMINI_API_KEY`. `tools/listen.py` uploads files to Gemini and
asks a question about them:

```bash
uv run tools/listen.py --model gemini-3.5-flash "question" file1.wav [file2.wav ...]
```

Pass `--model gemini-3.5-flash`: the default, `gemini-3.8-flash`, was often unavailable (503), and
Pro models may have no quota on your key. Scores drift by one point between identical calls, and
it occasionally hallucinates (it has heard voiceovers in instrumental files). Use it for direction,
for A/B comparisons and for catching misreads, never for a single-call pass or fail, and
cross-check what it says. It also watches video, so it can comment on a preview.

Without a key the lead reviews audio with ffmpeg measurements only ([How the lead reviews without
watching](#how-the-lead-reviews-without-watching), [Snippets](#snippets)): loudness and true peak
with `ebur128`, and gaps with `silencedetect`.

```bash
ffmpeg -i master.mp4 -af ebur128=peak=true -f null - 2>&1 | rg 'I:|Peak:'
ffmpeg -i take.wav -af silencedetect=noise=-40dB:d=0.25 -f null - 2>&1 | rg -o 'silence_(start|end): [0-9.]+'
```

### Music

Owner: the composer. Folder: `music/`.

**A video without music** has no composer and no `music/arrangement.py`. `edit/mix.py` then has no
music bed, and the credits list no samples ([The mix](#the-mix)). A score of synthesized
instruments only (`pluck`, `sub`, the synthesized percussion) needs no sample libraries
(`./setup.sh --no-samples`); a sampled instrument without them stops the render with a message
naming the missing folder.

**Score as code.** The composer writes the score as Python data (motifs, harmony, parts, an
arrangement per section) and renders it with a small sampler: nearest sample per note and
velocity, repitching for small intervals, release tails, round-robins, humanised timing, then
convolution reverb and mastering to -16 LUFS, with sample-aligned stems (piano, strings, mallets,
bass, percussion, synth, winds). Only the piano and orchestral samples come from the libraries;
kick, claps, snaps, sub bass, synth pluck, risers and the reverbs are synthesized
(`scorekit/synth.py`, `scorekit/mix.py`).

**The project's score** is `music/arrangement.py`, defining `compose(seed: int) -> Score`;
`render.py` calls it, renders every note and writes the manifest from the score's grid. A
skeleton with placeholder numbers:

```python
from scorekit import drums as D
from scorekit.parts import Dyn, bass, melody, ostinato
from scorekit.score import Score
from scorekit.timing import Grid

GRID = Grid(bpm=120.0, bar0_at=2.0, total=180.0,       # total: the picture's end, fade tail included
            local=[],                                    # (first bar, bars, seconds) at their own tempo
            sections=[("open", 0, 0.0), ("pitch", 13, 23.5)])   # (id, first bar, picture cut in s)
HARMONY = [(0, 2, "C"), (2, 2, "Am7"), (4, 2, "F"), (6, 2, "Gsus4")]   # (bar, bars, chord)
HOOK = [(0, 0.5, 69), (0.5, 0.5, 71), (1, 1, 74), (2, 2, 76)]          # (beat, beats, MIDI pitch)


def compose(seed: int) -> Score:
    sc = Score(GRID, HARMONY, seed)
    ostinato(sc, "piano", 0, 8, ("r", "5", "9", "5", "3", "5", "9", "5"), 60, Dyn(70))
    melody(sc, "glock", 4, HOOK, 80)
    bass(sc, 0, 8, 72)
    D.kick(sc, 0, 8, 90)
    D.backbeat(sc, 0, 8, 82)
    sc.auto("piano", 6, -3.0)                            # stem gain breakpoint: -3 dB at bar 6
    return sc
```

The engine's pieces:

- **`Score`** (`scorekit/score.py`): `add(inst, beat, beats, pitch, vel)` places a note (beats count
  from bar 0: bar 13 beat 3 is `13 * 4 + 2`), `chord(...)`, `hit(kind, beat, vel)` for percussion,
  `auto(stem, bar, db)` for stem gain, `spans(start, end)` and `chord_at(bar)` read the harmony.
  Timing and velocity are humanised per instrument.
- **`Grid`** (`scorekit/timing.py`): the tempo map and bar grid: `t(bar)`, `beat_t(beat)`,
  `bars_at(seconds)`, `manifest()`. Its speech windows come from `narration/timeline.json` for the
  QC plots.
- **Textures** (`scorekit/parts.py`): `ostinato` (broken chords from the harmony, with accent
  shapes `ACCENT_332` and `ACCENT_EVEN`), `block_chords`, `bass` (`eighths`, `pulse`, `long`),
  `melody`, `pad`, `soar`, `sparkle`, `flourish`, `harp_run`. `scorekit/theory.py` parses chord
  symbols and voices chords.
- **Drums** (`scorekit/drums.py`): `kick`, `backbeat`, `shaker`, `tambourine`, `clicks`, `fill`,
  `build` (a crescendo into a downbeat), `crash`.
- **Instruments**: sampled `piano`, `vln_spic`, `vla_spic`, `vc_spic`, `cb_spic`, `vln_pizz`,
  `vla_pizz`, `vc_pizz`, `cb_pizz`, `vln_sus`, `vla_sus`, `vc_sus`, `harp`, `marimba`, `xylo`,
  `glock`, `horn`; synthesized `pluck` and `sub`; percussion `kick`, `clap`, `snap`, `riser`,
  `sub_drop` (synthesized) and `bdrum`, `snare`, `click`, `shaker`, `tamb`, `tom_lo`, `tom_hi`,
  `taiko`, `cym_hit`, `cym_swell`, `cym_swell_short`, `triangle`, `fingcymb`, `chimes` (sampled).
  Keep `music/CREDITS.md` true to the libraries the score uses.

**The arrangement follows the timeline.** The tempo and bar grid are chosen so scene cuts land
within about 0.3 s of a downbeat or a half bar, and melodies thin out inside speech windows. When
the timeline changes, the score re-renders in under a minute with the same character; the tempo
may shift a few BPM. No single tempo puts every cut on a downbeat: weight the cuts that matter
most (the logo reveal, the close), let the others fall on half bars, and keep within any tempo
range the human has set. Record the fit in `HANDBOOK.md`: tempo, bar 0, which cuts land on
downbeats or half bars, and the worst offset. When a section's length is fixed and the bars do
not fit, give it a `local` tempo that spans it exactly; the manifest's `tempo_map` records it, and
every later section keeps its offset from its cut.

**An arc per section**, agreed with the human: what the music does under the problem statement,
on the logo reveal, under the product name, under dense explanation, in the strongest section and
at the close. Techniques that serve any arc: rest the melody about 10 dB lower under the product
name; ease under dense explanation with a 3 dB stem duck; let the hook and the pulse carry an
arrival instead of a new sustained layer entering on it; resolve the close to a chord held under
the end card. Under a single credit line, the end card's chord can ring on with one soft touch and
fade to silence; a reprise is not needed.

**Taste comes from the brand and the human.** Start from `BRAND.md`, "Music and sound feel", and
the composer's part of the HANDBOOK "Brand" section. Ask what each reference means to this person:
a game soundtrack or a genre name can mean a tempo and an energy to one listener and an
instrumentation to another, and a misread reference costs a whole score. Record every rejection
with its reasons in `NOTES.md` ([Rejected styles](#rejected-styles)), keep rejected scores' code
and renders in a reference folder, and escalate the composer one tier after two failures, with
both attempts and the feedback as evidence.

**Checking without ears**: numbers (onset density, tempo estimate, spectral centroid, loudness
curve, click detection, from `--qc`) and the judge, asked pointed questions (rate each quality
`BRAND.md` asks for and each quality of a rejected score 1-10; name the instruments heard) and
compared against the rejected version.

```bash
cd music
uv run render.py --selftest    # eight synthesized bars -> out/selftest/; checks the engine, no samples needed
uv run render.py --qc          # render (~50 s for a full cue) plus QC plots in out/qc/
uv run render.py --excerpt A B # a slice from A to B seconds, for the judge
uv run render.py --qc-only     # re-analyse the existing files
```

`manifest.json` holds the bpm, `bar_0_at`, downbeats, beats, sections (with `offset_from_cut`),
speech windows and any `tempo_map`.

### Motion graphics

Owner: the motion designer. Folder: `motion/` (Python 3.12, skia-python on the GPU through
OpenGL: EGL on Linux, CGL on macOS). Run everything from `motion/`:

```bash
uv run python render.py --selftest                                       # the kit's test scene: GPU, fonts, encoder
uv run python render.py <scene> --duration 22.83 --handle 0.5            # opaque .mp4
uv run python render.py <scene> --duration 22.83 --handle 0.5 --alpha    # ProRes 4444 _alpha.mov
uv run python render.py <scene> --contact                                # 9-frame contact sheet
uv run python render.py <scene> --still 12.0 [--over <hex>]              # one PNG, optionally composited
./render_all.sh                                                          # every scene in scenes.txt, both variants
```

Without narration, a section's on-screen words are its `text` in `narration/sections.json`, which
also sets its length ([A section without a take](#a-section-without-a-take)). A scene can read its
text from there, so the words and the timing come from one place.

**Start from the brand.** `design.json` supplies the fonts and colours; `BRAND.md`, "Imagery and
motion feel" and "Logo", and the motion part of the HANDBOOK "Brand" section say how things move
and how the logo may be used.

**A scene** is a module `motion/scenes/<name>.py` that defines `SCENE`, a subclass of
`lib.scene.Scene`; `render.py <name>` loads it. A skeleton:

```python
from lib import gfx
from lib.ease import cubic_out, seg, smooth
from lib.scene import Scene


class Title(Scene):
    name = "title"           # the module name: out/title.mp4
    key = "open"             # the timeline scene it belongs to
    nominal = 6.0            # its window in narration/timeline.json
    marks = [(0.5, "title in"), (4.0, "title out")]

    def draw(self, canvas, t, opaque):
        u = self.u(t)                       # nominal seconds, whatever --duration is
        a = smooth(seg(u, 0.5, 1.3)) * (1 - smooth(seg(u, 4.0, 4.6)))
        y = 560 - 12 * cubic_out(seg(u, 0.5, 1.6))
        gfx.text(canvas, "<a line from the script>", 960, y, 52, gfx.FG, 500, 0.0, a, align="center")


SCENE = Title
```

- `draw(canvas, t, opaque)` paints one frame on a skia canvas in 1920x1080 logical units (the
  renderer supersamples at 2x); `t` is seconds into the window. The renderer clears an opaque
  frame to `gfx.BG` and a transparent one to nothing before it calls `draw`; `opaque` is False
  for the transparent variant, which must leave out any ground the scene paints itself. Set
  `alpha = True` for a scene that is transparent by default. `setup()` (optional) builds state
  that does not depend on time.
- Each scene is parametric in duration, so a timeline change is one command: author it in
  nominal seconds through `self.u(t)`; `--duration` retimes it uniformly (every beat scales), and
  `out/manifest.json` carries the retimed `marks` per file.
- The engine's helpers: `lib/gfx.py` (the colours `BG`, `FG`, `FG2`, `ACCENT` from `design.json`
  and `HAIR`, `CARD` mixed from them; `typeface(weight, italic=False)`, `font(size, weight=400,
italic=False)`, `text`, `text_width`, `text_glow`, `label`, `card`, `pill`, `hairline`,
  `soft_stroke`, `glow_stroke`, `glow_dot`, `col`, `mixcol`), `lib/logo.py` (the logo from
  `design.json`, [The logo in a scene](#the-logo-in-a-scene)), `lib/ui.py` (`persp_matrix` for a
  tilted pane, `status_glyph`, `edge_path`, `trimmed` and `draw_edge` for connectors drawn in
  over time, `port`, `CodeLines` for typed code), `lib/ease.py` (`seg`, `lerp`, `smooth`,
  `cubic_io`, `quint_io`, `back_out`, `spring`, `stagger`, `ease_in_linear`, ...). `text`,
  `text_width` and `text_glow` default to weight 400, `text_glow` to `ACCENT`. A helper several
  scenes share goes in `lib/` beside them.
- **`scenes.txt`** lists what `render_all.sh` renders, one scene per line with its `render.py`
  arguments, usually the window from `timeline.json`:

  ```text
  # scene   arguments
  title     --duration 6.1
  steps     --duration 18.32
  ```

  Each line renders the scene's default and, when that is opaque, its transparent variant
  (`--variants`), with 0.5 s handles.

- `--alpha` writes a transparent ProRes 4444 `.mov` of an opaque scene, leaving out the
  background, so the editor can place it over any ground. `--opaque` forces H.264. A full-frame
  scene that paints its own ground stays opaque; other scenes are composited through alpha.
- Every clip has 0.5 s handles; manifest marks include the handle, so clip time = master time -
  scene start + 0.5.
- Alpha variants draw in the same colours as the opaque render. Check a transparent still
  composited over the colour it will sit on (`--still t --over <design.json background>`), and
  over a capture or b-roll frame if the edit places it there.
- Render intermediate buffers in RGBA F16. 8-bit premultiplied accumulation of a temporally
  blurred log produced blocky glyphs.

**GPU gotchas**, both from mixing skia and moderngl on one GL context:

- On Linux, `skia.GrDirectContext.MakeGL()` returns `None` under a moderngl EGL context, because
  skia's native interface there is GLX's; `skia.GrDirectContext.MakeGL(skia.GrGLInterface.MakeEGL())`
  works, with the NVIDIA driver and with Mesa (about 10 ms per 4K frame with blurs on an NVIDIA
  GPU). On macOS the native interface is CGL's, so `lib/gfx.py` calls `MakeGL()` with no argument.
- skia's flush leaves `GL_BLEND` enabled and moderngl does not reset it, so an uncleared
  framebuffer accumulates across frames: single stills look right while the encoded movie
  saturates to opaque white. A moderngl shader pass added to the renderer must call
  `fbo.clear()` and `ctx.disable(moderngl.BLEND)` first. Verify alpha by decoding the encoded
  `.mov`, never only from stills.

Keep a table of the scenes in `HANDBOOK.md`: name, window, duration, content. Scene guidance from
a finished video:

- An opening scene that dramatises a problem (a dial, an odometer, a counter) needs a designed
  ground (a flat gray open reads as dull), nothing cut off at the edges (a percentage clipped on
  the right reads as spartan), and no decorative marks a viewer could find confusing (radial scar
  ticks, comparison bars).
- A table scene: typographic and uncluttered; an accent bar that hops between rows fades and never
  crosses glyphs; no axis touching its container.
- A diagram or graph: built from real data (the fixture story or the product's real output),
  solid lines for facts and dashed for inferred ones, sized from measured content; put the beat
  the narration lands on last.
- A sequence of steps or checks: a cascade, a stepper and a ledger of results. Place call-out
  cards so they never overlap prompt text.
- A scene showing a terminal session with a third-party tool (a coding agent, say): one person,
  unnamed, working in it; the tool's banner shows the installed version; show a document's prose
  first, then scroll to its structured parts with call-outs.
- An end card: the logo (`logo.draw`, within `BRAND.md`'s clear space and minimum size),
  tagline, URL; a licence line only if the human wants one.

### Web capture

Owner: web capture. Folders: `fixtures/web/` to `captures/web/`.

The agent runs no real workload of the product. It writes a Python aiohttp mock of the product's
server that serves the real built frontend (`PRODUCT_WEB_DIST`) and implements the API the
frontend calls, from the frontend's own schema, driven by a scripted clock: snapshots that follow
the fixture story, settings endpoints, and any live stream the UI shows (a terminal websocket can
replay a scripted coding-agent session built with `webcap/agent_session.py`, which redraws the
way an Ink terminal UI does: sober text, a spinner, an input box).

Capture is deterministic frame stepping (Playwright, Chromium, 1920x1080 at device scale 2,
giving 3840x2160 at 60 fps): for every frame the mock's clock, the page's faked clock and every
CSS animation advance to the same instant, then a screenshot ([Snippets](#snippets)). Zero
frame-time jitter. Files are written to `.tmp` and renamed atomically. `manifest.json` has marks,
`key_marks` and a per-frame cursor track: headless browsers have no cursor, so the editor draws
it, along with the click on native select popups, which do not render headless.

**The project's module** is `fixtures/web/product.py` (loaded by `webcap/project.py`):

| Name               | Required | Meaning                                                                                                        |
| ------------------ | -------- | -------------------------------------------------------------------------------------------------------------- |
| `World`            | yes      | a subclass of `webcap.world.World`, built with no arguments: the scenes' clocks and the mock's state           |
| `build_app(world)` | yes      | the aiohttp `web.Application`: the product's API routes, then `serve_dist(app, dist)`                          |
| `CLIPS`            | yes      | `{name: async def clip(world, browser, out_dir, scale) -> (Clip, Page)}`                                       |
| `LOCAL_STORAGE`    | no       | `{key: value}` written to the page's localStorage (as JSON) before it loads, for a theme or a dismissed banner |
| `THEME`            | no       | a label the manifest records                                                                                   |
| `FONT_PROBES`      | no       | `(scene, path, {label: CSS selector})`: the manifest reports which font files each element rendered with       |

A skeleton (`story.py` is your fixture story as code; the routes are your product's):

```python
import json

from aiohttp import web

import story
from webcap.browser import open_scene
from webcap.server import require_env, serve_dist
from webcap.world import Clock, World as BaseWorld

LOCAL_STORAGE = {"<app>:theme": "dark"}
SCENES = {"overview": Clock(((0.0, 0.0), (20.0, 3200.0)))}   # 20 clip seconds tell 3200 story seconds


class World(BaseWorld):
    def __init__(self):
        super().__init__(SCENES)
        self.sockets = set()
        self.last = None

    async def tick(self, t):
        await super().tick(t)
        body = json.dumps(story.snapshot(self.story_s()))
        if body != self.last:                   # publish on change, as the real server does
            self.last = body
            for ws in list(self.sockets):
                await self.send(ws, body)       # send() counts messages; the director waits for each


def build_app(world):
    async def updates(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        world.sockets.add(ws)
        world.last = None                       # a new page gets the current state at once
        try:
            async for _ in ws:
                pass
        finally:
            world.sockets.discard(ws)
        return ws

    app = web.Application()
    app.router.add_get("/api/updates", updates)
    serve_dist(app, require_env("PRODUCT_WEB_DIST", "point it at the product's built web frontend"))
    return app


async def overview(world, browser, out_dir, scale):
    d = await open_scene(world, browser, out_dir, "overview", "/", scale)   # warmed up: t = 0 is settled
    d.start("w1_overview")
    await d.hold(1.0)
    x, y = await d.center("<selector of what the narration names>")
    await d.glide(x, y, 0.8)
    await d.click()
    d.mark("dialog opens", key=True)            # key marks are what the edit syncs to
    await d.hold(2.5)
    d.still("w1_overview_final")
    return d.finish(), d.page


CLIPS = {"w1_overview": overview}
```

The director (`webcap/director.py`) records from `start(name)` to `finish()`; between them
`hold(s)`, `glide(x, y, s)`, `click()`, `type(text)`, `press(key)`, `center(selector)`,
`mark(event, key=True)` and `still(name)` each advance whole frames. `Clock` maps clip seconds to
story seconds piecewise-linearly, so a clip can race through a long run and then play at wall
speed; its `epoch` sets the page's wall clock. Override `World.set_scene` to reset the mock's
state between clips.

```bash
cd fixtures/web
export PRODUCT_WEB_DIST=/path/to/product/web/dist PRODUCT_REPO=/path/to/product
uv run python -m webcap.capture && uv run python -m webcap.verify   # every clip, then smoothness
uv run python -m webcap.capture <clip>                                # one clip
uv run python -m webcap.capture <clip> --draft --out /tmp/x           # quick 1x check
uv run python -m webcap.server --scene <scene>                        # live preview at http://127.0.0.1:7373/
uv run python -m webcap.probe <scene> --out /tmp/p 0.5 3 8            # screenshots at clip times
```

A full set of clips took about 33 minutes in the finished video. Keep a table of clips with
lengths and key marks in `HANDBOOK.md`.

**Faithfulness**: show only what the real UI renders. When the real UI has a quirk (a counter
that stays 0 during an event, a label that repeats a word), keep the real behaviour and record it
as a bug in the product's own tracker instead of faking it.

### TUI capture

Owner: TUI capture. Folders: `fixtures/tui/` to `captures/tui/`.

The real product binary runs in a pseudo-terminal at a fixed grid size; `pyte` interprets its
output; each screen state is drawn with skia in the mono font from `design.json` (or the system
monospace font), with procedural box drawing so lines join cleanly. The cell size is fitted to
the font, and bold and italic are synthesised, so any monospace font works. The background and
text colours come from `design.json`; the other terminal colours are softened ANSI colours in
`src/tuicap/palette.py`, and `TRUECOLOR` maps colours a program hard-codes onto them. The
captures part of the HANDBOOK "Brand" section says how close the terminal should stay to the
product's real theme.

**The project's module** is `fixtures/tui/product.py`, loaded by the `tuicap` command
(`src/tuicap/clips.py`). It defines `CLIPS`, `{name: function() -> (Recording, marks)}`, and may
define `prepare()` (builds the fixture workspace; runs before capturing), `STILL_T` (`{name:
seconds}` for each clip's still; default its last frame), `TRUECOLOR` (`{hex: palette hex}` for
colours the program hard-codes) and `SOURCE` and `NOTES` (text for the manifest). A skeleton:

```python
import os
from pathlib import Path

from tuicap.capture import clean_env, prompt, record_pty, run_capture_output, synth_cli
from tuicap.render import Recording

HERE = Path(__file__).resolve().parent
BIN = os.environ.get("PRODUCT_BIN", "<product>")
HOME = HERE / "home"                     # scratch HOME holding fixture config
DROP = ("<PRODUCT>_",)                   # the product's own variables never reach a capture


def t1_help():
    """A typed command and its real output, cut at a line boundary to fit the grid."""
    out = run_capture_output([BIN, "--help"], HERE, clean_env(HOME, drop=DROP), 120)
    return synth_cli(prompt("~/project"), f"{BIN} --help", out, 120, 30, seed=1)


def t2_live():
    """An interactive view, recorded live; keys are sent on a schedule."""
    events, inputs = record_pty([BIN, "<live view>"], HERE / "ws", clean_env(HOME, drop=DROP),
                                140, 26, [(6.0, b"q")], total=6.5)
    return Recording(140, 26, events, 6.0, inputs), [{"t": 0.5, "event": "first screen"}]


CLIPS = {"t1_help": t1_help, "t2_live": t2_live}
```

Engine pieces: `capture.record_pty(argv, cwd, env, cols, rows, actions, total)` records a program
with timed keystrokes; `run_capture_output` runs a command in a pty so it colours;
`synth_cli(prompt, command, output, cols, rows, seed)` builds a typed-command shot around real
output; `typing_schedule` gives human cadence; `clean_env(home, tz, drop)`; `Recording` times are
seconds from the video start, negative for pre-roll. `tmux_clip.tmux_server(socket, tmpdir, env,
conf)` runs an isolated tmux server and `tmux_clip.record_shell(...)` records an operator typing
into a shell, for a shot inside tmux.

Lessons from a finished video:

- A TUI that talks to a daemon over a socket needs a stand-in daemon in `fixtures/tui/` that speaks
  the product's wire format and plays the fixture story; a real run would start real work.
- Build the fixture workspace with the product's real init command in `prepare()`. Run config UIs
  with `HOME` pointed at a scratch home.
- A tmux shot: isolate it with `TMUX_TMPDIR` inside the fixture so the user's tmux is never
  touched, and keep that path short: a Unix socket path holds about 104-108 bytes, and
  `tmux_server` refuses a longer one.
- CLI clips run read-only commands against `PRODUCT_REPO`. Some commands refresh a cache there, a
  known side effect.

```bash
cd fixtures/tui
export PRODUCT_REPO=/path/to/product PRODUCT_BIN=<product>
uv run tuicap --selftest         # a canned clip; checks the renderer, needs no product
uv run tuicap                    # all clips (about 100 s for a set of eight)
uv run tuicap --only t2_live     # one clip, keeping the rest of the manifest
```

Keep a table of clips with sizes and key times in `HANDBOOK.md`; note any that exist but are
unused.

### B-roll

Owner: b-roll (or the lead). Folder: `broll/`.

B-roll is optional, chosen at kickoff. Without it there is no b-roll workstream, the EDL's
`BROLL_CLIPS` stays empty and the credits list none. Generated b-roll needs `GEMINI_API_KEY`.

Generate b-roll with Gemini Omni only, never Veo: reviewers rejected Veo output as poor.
`broll/gen/shots.json` is a list of `{"id", "prompt"}`; `genvideo.py` fixes the format (16:9,
1080p), and Omni returns about 10 s at 24 fps per shot. The script renders three shots at a time,
retries a failed shot once, skips ids already rendered, and writes `broll/gen/omni/<id>.mp4` plus
`<id>.json` (prompt, config, timing, attempts).

```json
[
  {
    "id": "01_server_aisle",
    "prompt": "Slow dolly along ... No people. Photorealistic documentary footage, 35mm lens, shallow depth of field, natural film grain."
  }
]
```

```bash
uv run tools/genvideo.py [--only <shot id>]   # from the project root; needs GEMINI_API_KEY
```

- Write prompts as a shot description: camera move, subject, light, "No people", then the look
  ("Photorealistic documentary footage, 35mm lens, shallow depth of field, natural film grain"),
  taken from `BRAND.md`, "Imagery and motion feel".
- Render several shots, cut a reel, and let the human pick.
- Pick imagery that matches what the narration says at that moment: an unrelated object under a
  sentence confuses the viewer.
- Normalise the chosen clips to `broll/candidates/NN_<id>.mp4` (H.264 crf 10, no audio) and list
  them in `edl.py`'s `BROLL_CLIPS`; the edit grades them (30 % saturation, 50 % brightness worked)
  so they sit under graphics.
- The lead checks every contact sheet: an agent's "no logos" claim once missed two branded clips.
- Generated footage needs no attribution.

Creative Commons stock is a last resort, and reviewers often reject it as off-message. If you use
it: search with an up-to-date `yt-dlp` (an outdated one only got 360p streams), check each
candidate's licence field for Creative Commons Attribution, cut short segments, make contact
sheets, and record title, channel, URL, licence and the range used in `broll/CREDITS.md`
([Subtitles and credits](#subtitles-and-credits)).

### The edit

Owner: the editor. Folder: `edit/`.

```bash
cd edit
uv run bg_test.py [seconds]   # self-test (default 6 s): background and a test window -> out/bg_test.mp4
uv run words.py            # faster-whisper word timings -> build/words.json (rerun after any narration change; empty without narration)
uv run mix.py              # narration chain + ducked music + sound design -> out/mix.wav (-14 LUFS)
uv run subs.py             # out/intro.srt (none without narration)
uv run credits.py          # out/CREDITS.txt
uv run render.py --preview                 # 540p30, no grain, DOF or motion blur -> out/preview.mp4
uv run render.py --range 14 30             # a time range only (any mode)
uv run render.py --contact --every 2       # contact sheets
uv run render.py --frames 0 25.8 166.5     # single frames -> build/frames/ (--full-frames for full quality)
uv run render.py                           # full master -> out/intro.mp4 (~3-4 min on a GPU)
uv run render.py --fast                    # full quality with the fast encoder (as previews use)
```

**`edl.py` is the edit as data**: which source, which in-point (by manifest mark or by spoken
word), which camera move, which transition. The project writes it; `editkit/project.py` loads it
for `render.py`, `mix.py` and `credits.py`. It defines `END` (the last frame, in seconds) and
`build() -> Timeline`, and optionally `BROLL_CLIPS` (b-roll names the cut uses, for the credits)
and `BUSY` (scene keys where the mix ducks the melody further). A skeleton:

```python
from editkit import cards
from editkit import credit_data as cd
from editkit.assets import resolve
from editkit.ease import Track
from editkit.scene import Camera, Segment, Timeline, Transition
from editkit.shots import browser, framed, fullframe, scene_starts, sync, timeline

S = scene_starts()                       # scene key -> start, from narration/timeline.json
TOTAL = timeline()["total"]              # end of the narrated picture
END = TOTAL + 5.0                        # plus the credit line's slot
BROLL_CLIPS = []                         # b-roll names the cut uses, for the credits
BUSY = ()                                # scene keys where the mix ducks the melody further


def motion(key: str, scene: str, start: float, end: float, **kw):
    """A motion clip clock-locked to its scene window: clip time = master - scene start + handle."""
    handle = float(resolve(key).entry.get("handle", 0.0))
    return fullframe(key, start, end, src_in=start - S[scene] + handle, **kw)


def build() -> Timeline:
    first = fullframe("still:motion/out/title_00.00.png", 0.0, 1.3, fade_out=0.55)   # the designed first frame
    title = motion("motion:title", "open", 0.0, S["pitch"] + 0.8)
    t = S["pitch"]
    ui = browser("web:w1_overview", t, S["end"])
    ui.src_in = sync("web:w1_overview", "dialog opens", t + 1.0, t, default=1.8)
    framed(ui, [(t, (0.5, 0.5, 1.05, 2.0, -3.0)), (t + 1.5, (0.5, 0.45, 0.7, 1.0, -1.0), "quint")])
    card = cards.credit_line("credits", cd.lines(BROLL_CLIPS))
    segs = [Segment("open", 0.0, [title, first]),
            Segment("pitch", t, [ui], Camera(aperture=4.0), Transition("push", 0.7)),
            Segment("credits", TOTAL, [fullframe(card, TOTAL, END + 1)], trans=Transition("dissolve", 0.6, ease="sine"))]
    fade = Track((0.0, 0.0), (END - 1.9, 0.0), (END - 0.5, 1.0, "sine"))
    return Timeline(END, segs, fade=fade)
```

- **Asset keys** name sources: `motion:<scene>` and `motion_alpha:<scene>` (motion's opaque and
  transparent files), `web:<clip>`, `tui:<clip>`, `broll:<clip>`, `still:<path>`, `image:<card>`
  (`editkit/assets.py`). `resolve(key)` gives the file, its probe, its manifest entry and its marks;
  a missing asset becomes a placeholder of the right shape.
- **Shot helpers** (`editkit/shots.py`): `scene_starts()`, `timeline()`, `word(section, text)` and
  `word_end(...)` (master time of a spoken word, from `build/words.json`; lookups are strict, so a
  missing word fails the build and a shot can open on a named word without drifting;
  `narration(name)` and the word lookups raise a `KeyError` for a silent section),
  `sync(key, event, at, start)` (the in-point that puts a manifest mark at a master time),
  `anchor(...)`, `fullframe`, `browser` and `terminal` (a plane dressed as a window), `framed`
  (drive a window's position, scale and tilt from framings of its content), `cursor_for(key)`
  (the capture's cursor track).
- **The scene model** (`editkit/scene.py`): a `Plane` has a source, a time span, `src_in`,
  `speed`, `hold`, `pos`, `rot`, `scale`, `opacity`, `blur`, `dim`, `saturation`, `view` (a crop),
  `fade_in`, `fade_out` and window `chrome`; any of them can be a `Track` of keyframes
  (`editkit/ease.py`). A `Segment` groups planes under a `Camera` (`aperture` for depth of field)
  and enters with a `Transition`: `kind` (`cut`, `dissolve`, `push`, `zoom`), `dur`,
  `direction` (where a push sends the outgoing scene) and `ease`. During a transition each
  segment's group is drawn with a `GroupState` (`opacity`, `offset`, `zoom`). A
  `Timeline(total, segments, fade, background_level)` carries the fade to black (0 to 1) and a
  brightness multiplier for the background; both can be `Track`s.
- Scene windows come from `timeline.json`, word sync from `words.json`, capture in-points from
  manifest marks. Motion scenes are clock-locked to their windows.
- **The compositor** (`editkit/compositor.py`, moderngl over EGL on Linux or CGL on macOS, chosen
  with the encoder and decoder in `editkit/hw.py`): sources decoded through ffmpeg pipes, layers
  on 3D planes with perspective-correct sampling and mipmaps, window chrome and soft shadows,
  per-layer depth of field, shutter motion blur, the cursor drawn from the capture's track, the
  background, bloom and grain, frames piped back to ffmpeg. `shaders/` holds the GLSL
  (background, plane, group, dof, bloom, shadow, final). The background is flat: `design.json`'s
  `background` colour, scaled by `Timeline.background_level`, with grain (`design.json`'s
  `grain`; the preview renders without grain). `cards.py` draws the credit line.
- **Design**: the edit reads the fonts, `background`, `text`, `secondary` and `grain` from
  `design.json` (`editkit/design.py`, `editkit/art.py`); window chrome is a fixed neutral grey.
  Placeholders are cached in `edit/build/placeholders/`: delete them after `design.json`
  changes.
- **The render guard** refuses a full render while any shot resolves to a placeholder, and prints
  each key still on one (`--allow-placeholders` for drafts).
- **Colour**: untagged H.264 sources are decoded as BT.601, because motion clips are encoded with
  ffmpeg's default BT.601 matrix and left untagged.
- **Handles and manifests**: motion clips carry a 0.5 s handle, honoured by the edit. Manifests
  are read by file name, so a stale entry cannot shadow the current file.
- **The first frame**: hold a designed still from motion as it is ([Phase 5](#phase-5-finishing)).
  Repairing a frame in the edit (replacing its background, say) leaves artefacts; fix it at the
  source.
- **The open and the reveal**: a hold on the first frame with a fade, then the logo reveal in a
  silent window, then a narration line (the product name) once the logo is settled.
- **The end card**: the logo, tagline and URL as `BRAND.md` and the editor's part of the
  HANDBOOK "Brand" section describe them, usually a motion scene; the credit line dissolves in
  after it.
- **The end**: a real fade to black (~2.5 s, eased), then a pure-black hold. Transparency, grain
  and dither fade with the picture, or black stays above Y=16; verify with `signalstats`.

### The mix

`edit/mix.py` writes `out/mix.wav`: the narration chain (high-pass, presence, de-essing, light
compression, voice at about -18 LUFS), the music ducked 8.5 dB under speech (rhythm stems only
4.5 dB) with a hold and smooth ramps so gaps swell back up, a further melodic duck in the EDL's
`BUSY` scenes where a dense score meets dense narration, quiet UI sound design (whooshes on
`push` and `zoom` transitions, ticks on cursor clicks) placed from the edit decision list, and mastering to
-14 LUFS integrated with true peak under -1 dBTP (the limiter sits at -1.6 dBTP to leave margin
for AAC overshoot).

Every part is optional. Without narration there is no voice bus and nothing ducks the music.
Without a soundtrack (`music/out/soundtrack.wav`) there is no music bed. With neither, the sound
design keeps its own level: there is no loudness target, only the limiter. With no sound design
either, the mix is silence of the EDL's length, so the master still gets an audio track.

### Subtitles and credits

`edit/subs.py` builds `out/intro.srt` from the narration scripts (`narration/NN_name.txt`) and the
whisper word times (lines of at most 42 characters). A video without narration has no subtitles:
`subs.py` writes nothing and says so.

Credits are data, so the on-screen card and the video description (`out/CREDITS.txt`, from
`edit/credits.py`) cannot disagree:

- `music/CREDITS.md` records each sample library: source, files, licence, what it is used for.
  `credit_data.music_samples()` credits only the libraries whose licence requires attribution
  (CC0 ones are left out), and none without a soundtrack.
- `broll/CREDITS.md` gets a `## <clip name>` section with `- Title:`, `- Channel:`, `- URL:`,
  `- Licence:` and `- Range used:` lines for every CC BY clip. `credit_data.broll()` credits only
  clips with a section, so generated clips (no section) get no row, and a video without b-roll
  none.
- `edit/credits.json` (optional) holds the description's title line and any row the human asks
  for: `{"title": "<product>: introduction", "rows": [["Narration", "Gemini TTS (<voice>)"]]}`.
- `credit_data.lines(BROLL_CLIPS)` gives the on-screen lines; `cards.credit_line(name, lines)`
  draws them as a full-frame transparent card the EDL places as `image:<name>`.

Show only what a licence requires: CC BY samples or footage, and a typeface only if its licence
asks for on-screen credit (most font licences, the SIL Open Font License among them, do not). No
row for generated b-roll, CC0 samples or the narration, and no row naming an AI tool. The credits
are real end credits on screen, never a box that points elsewhere. The card is one subtle centred
line on the background (about 22 px, secondary text colour; no heading, rule or page number),
dissolved in from the end card and short: about 5 s including the fade to black. Each further credit adds a
line, never a page that outstays its content.

## Brand

The brand decides how the video looks, speaks and sounds. A project keeps it at its root, in two
optional places: `BRAND.md`, the guidelines in prose, and `brand/`, the files. `BRAND.md` is the
source of truth. The brand skill turns it into `design.json`, which the renderers read
([Design system](#design-system)), and into the "Brand" section of `HANDBOOK.md`, which every
brief points to. Without them the video renders in neutral defaults: system fonts, white text on
black, no logo.

They go in the project folder that `install.sh` created, never in the kit, so each video has its
own brand:

```text
~/<product>-video/          # the project, made by ./install.sh
├── BRAND.md                # the guidelines (the brand skill writes it if you have none)
├── brand/
│   ├── logo/               # SVG, or PNG at least 2000 px wide; a dark- and a light-background variant
│   ├── fonts/              # font files plus their licence files, a folder per family
│   ├── palette/            # optional exported palette files
│   └── reference/          # images or videos of the brand in use
├── design.json             # generated by the brand skill; never edit by hand
└── ...                     # the engine and the project's own files
```

The human can copy existing brand files in before the first session; otherwise the lead runs the
brand skill with the human: it creates `BRAND.md` and the `brand/` folders and says which files to add.

### `BRAND.md` and `brand/`

`BRAND.md` has these headings, in this order; the template ships at
`.claude/skills/brand/BRAND.template.md`:

| Heading                 | What it holds                                                                     |
| ----------------------- | --------------------------------------------------------------------------------- |
| Identity                | the product name as written and as spoken, a one-line description                 |
| Voice and tone          | how the script reads and the narrator sounds; words the brand uses and never uses |
| Colours                 | each colour as hex plus its role (background, text, secondary, accent, others)    |
| Typography              | the files in `brand/fonts/` and their roles: display, body, mono                  |
| Logo                    | files, variants, clear space, minimum size, do and don't                          |
| Imagery and motion feel | the visual mood, how things move, transitions liked or avoided                    |
| Music and sound feel    | genre, tempo, instruments, energy curve, what to avoid                            |
| Things to avoid         | colours, effects, words, imagery the video must not use                           |
| Legal                   | trademark lines, font licences, other notices                                     |

```text
brand/
  logo/        SVG preferred, or PNG at least 2000 px wide; variants for dark and light backgrounds
  fonts/       font files, with their licences
  palette/     optional exported palette files
  reference/   images or videos of the brand in use
```

### The brand skill

`claude-skills/brand/` in the kit, installed to `.claude/skills/brand/`. The lead runs it at
kickoff and again whenever `BRAND.md` or anything in `brand/` changes.

- **Without `BRAND.md`** it interviews the human, writes `BRAND.md` from the template and creates
  the `brand/` folders. The human then adds the logo and font files.
- **With `BRAND.md`** it maps `BRAND.md` and `brand/` to `design.json` (fonts by role, colours,
  grain, logo), runs the checker, writes a "Brand" section into `HANDBOOK.md` with a part for
  each workstream (narration voice and tone, music feel, motion, captures, edit), and lists gaps
  and conflicts as questions for the human.

`design.json` is generated: never hand-edit it. To change the look, change `BRAND.md` or
`brand/` and rerun the skill; then delete `edit/build/placeholders/` and re-render what shows the
change. `setup.sh` warns when `design.json` is older than `BRAND.md` or `brand/`.

### The checker

```bash
uv run .claude/skills/brand/check.py [project-root]
```

It prints one `ok`, `WARN` or `MISSING` line per check, then a summary with both counts, and
exits 1 on any MISSING:

| Check                                                                                        | Level when it fails |
| -------------------------------------------------------------------------------------------- | ------------------- |
| `BRAND.md`, `brand/` or `design.json` absent                                                 | MISSING             |
| `design.json` not valid                                                                      | MISSING             |
| `brand/logo`, `brand/fonts` or `brand/reference` empty or absent (an absent `palette` is ok) | WARN                |
| a font does not parse                                                                        | MISSING             |
| a font in `brand/` that `design.json` does not name (not checked when it names a family)     | WARN                |
| a font family `tools/fonts.py --check` cannot find                                           | MISSING             |
| a family that lacks the wanted weight or style, so another is used                           | WARN                |
| the mono font is not monospaced                                                              | MISSING             |
| the mono font lacks some ASCII characters                                                    | WARN                |
| a logo does not parse, or has the wrong extension                                            | MISSING             |
| a PNG logo under 2000 px wide                                                                | WARN                |
| WCAG contrast: text on background below 4.5:1, secondary below 3:1                           | WARN                |
| `design.json` older than `BRAND.md` or anything in `brand/`                                  | WARN                |

It is a single-file `uv` script with its own pinned dependencies (fonttools, pillow).

### The logo in a scene

`design.json` names the logo files, both optional:

```json
{
  "logo": {
    "on_dark": "brand/logo/<name>-on-dark.svg",
    "on_light": "brand/logo/<name>-on-light.png"
  }
}
```

`design.logo(variant=None)` returns the file. With no variant it picks `on_dark` when the
`background` colour's WCAG relative luminance is below 0.179, else `on_light`, and falls back to
the other variant when one is missing. An unknown variant raises `ValueError`; with no logo set
it raises `FileNotFoundError: no logo in <root>/design.json: name logo.on_dark or logo.on_light
(README.md, "Brand")`.

Motion scenes draw it with `motion/lib/logo.py`:

- `logo.draw(canvas, cx, cy, width, alpha=1.0, variant=None)` draws it centred at `(cx, cy)`,
  `width` px wide, aspect kept.
- `logo.size(width, variant=None) -> (w, h)` gives the drawn size, for layout.
- `logo.load(path)` (cached per path) and `logo.svg_size(path)` are the lower-level pieces.

An SVG is drawn through Skia's SVG module, a PNG through `skia.Image`. An SVG's size comes from
its numeric `width` and `height`, else its `viewBox`. Skia's SVG module draws filters, gradients
and masks, but draws nothing for `<text>`, CSS `<style>` class rules or an embedded `<image>`:
convert text to outlines and write styles as inline attributes, or export a PNG at least 2000 px
wide and name that instead. An end card:

```python
from lib import gfx, logo
from lib.ease import seg, smooth
from lib.scene import Scene


class EndCard(Scene):
    name, key, nominal = "endcard", "close", 6.0

    def draw(self, canvas, t, opaque):
        u = self.u(t)
        w, h = logo.size(480)
        logo.draw(canvas, 960, 480, 480, smooth(seg(u, 0.3, 1.2)))
        gfx.text(canvas, "<tagline>", 960, 480 + h / 2 + 90, 40, gfx.FG, 400, 0.0,
                 smooth(seg(u, 1.0, 1.8)), align="center")


SCENE = EndCard
```

Draw only the files in `brand/logo/`: never redraw, recolour or distort the logo. Keep
`BRAND.md`'s clear space and minimum size, and animate it only in ways its "Logo" do and don't
list allows. When `design.json` names a logo, the motion self-test draws it under the card,
fitted to a 320x130 box.

## Design system

The design system is the brand made concrete for the renderers: fonts, colours, grain, logo,
sizes and transitions. It lives in `design.json` and in the shared spec; the renderers read the
first, the agents the second.

### Defining the design

1. The human approves `BRAND.md` and supplies `brand/` ([Brand](#brand)).
2. The brand skill generates `design.json` and the HANDBOOK "Brand" section; the checker passes.
3. The lead renders the self-tests and one still per renderer that matters (a motion title, a
   terminal clip, an edit frame with a window) and shows them to the human before production.
4. The lead writes the design system into the shared spec and `HANDBOOK.md` as data: the four
   colours and their roles, the fonts by role and the sizes in use (hero, title, body, label), the
   logo variants with their minimum size, the grain, the transitions in use and what each one
   means, and the rejected styles. Colours the brand defines beyond the four go in the spec with
   where they may appear; scenes take them from there.
5. Every brief quotes the parts its workstream uses.

Rules that hold for any brand:

- The product's own UI keeps its own fonts and colours in captures; the product's state colours
  appear only where its UI shows them.
- Give opening scenes a designed ground, painted by the scene: a flat open reads as dull.
- Graph edges, connectors and text need strong contrast on any coloured ground.

### `design.json`

At the project root, optional, generated by the brand skill. Every key is optional; an unknown
key is rejected. Paths are relative to the project root.

```json
{
  "fonts": {
    "family": "<Body family>",
    "regular": "brand/fonts/<Body>-Regular.otf",
    "bold": "brand/fonts/<Body>-Bold.otf",
    "italic": "brand/fonts/<Body>-Italic.otf",
    "bold_italic": "brand/fonts/<Body>-BoldItalic.otf",
    "mono": "brand/fonts/<Mono>-Regular.otf",
    "weights": { "700": "brand/fonts/<Display>-Bold.otf" }
  },
  "colors": {
    "background": "#rrggbb",
    "text": "#rrggbb",
    "secondary": "#rrggbb",
    "accent": "#rrggbb"
  },
  "grain": 0.022,
  "logo": {
    "on_dark": "brand/logo/<file>.svg",
    "on_light": "brand/logo/<file>.png"
  }
}
```

| Key      | Meaning                                                             | Default                                    |
| -------- | ------------------------------------------------------------------- | ------------------------------------------ |
| `fonts`  | fonts by role (a file or a family name); `weights` maps a weight    | the system sans and monospace              |
| `colors` | `background`, `text`, `secondary`, `accent` as `#rrggbb`            | `#000000`, `#ffffff`, `#a0a0a0`, `#ffffff` |
| `grain`  | film grain strength, a number >= 0                                  | 0.022 (previews render with 0)             |
| `logo`   | `on_dark`, `on_light` ([The logo in a scene](#the-logo-in-a-scene)) | none                                       |

**Roles.** `design.json` has no display role: the brand skill puts the display face under
`fonts.weights` at the weights titles use, or under `bold`, and records which in `HANDBOOK.md`.
Body faces go under `regular`, `bold`, `italic` and `bold_italic`, the mono face under `mono`.

**Font lookup.** `font(weight, italic)` returns the file of the first role set among: for italic,
`bold_italic` (weight >= 600), then `italic`; then `weights["<weight>"]`; then `bold` (weight >=
600); then `regular`; then the system sans. `mono()` returns `fonts.mono`, else the system
monospace font.

**System fonts**: on Linux DejaVu Sans and DejaVu Sans Mono, found with `fc-match`, then under
`/usr/share/fonts/` (package `fonts-dejavu-core`, installed by `system-deps.sh`); on macOS
`/System/Library/Fonts/Helvetica.ttc` and `Menlo.ttc`.

**Errors.** A font or logo path that is set but missing raises an error naming the key and the
path; a family that `brand/fonts/resolved.json` does not resolve raises one telling you to run
`tools/fonts.py` ([Fonts by family](#fonts-by-family)). An invalid colour or grain raises an error naming this section. `setup.sh` reports either
as MISSING in its "Fonts" section.

**Loaders.** `edit/editkit/design.py`, `motion/lib/design.py` and
`fixtures/tui/src/tuicap/design.py` have the same API: `load()`, `color(name)`, `grain()`,
`font(weight=400, italic=False)`, `mono()`, `system(kind)`, `logo(variant=None)`.

### Fonts by family

A font role (`regular`, `bold`, `italic`, `bold_italic`, `mono`, `weights."<n>"`) is written in
one of two ways:

- **A file**: a path relative to the project root that ends in `.ttf`, `.otf` or `.ttc`. It must
  exist.
- **A family name**: anything else, such as `"Inter"` or `"JetBrains Mono"`. A family under a
  role means that family at the role's weight and style: `mono` is 400 upright, and `"Inter"`
  under `weights."800"` is Inter at 800.

`fonts.family` names one family for the four body roles: it fills `regular` (400), `bold` (700),
`italic` (400 italic) and `bold_italic` (700 italic) for each of them the file does not set
itself. `{"fonts": {"family": "Inter", "mono": "JetBrains Mono"}}` is a complete font setup.

Rendering reads files, so a family has to be turned into files first. From the project root:

```bash
uv run tools/fonts.py          # resolve every family-named role, write brand/fonts/resolved.json
uv run tools/fonts.py --check  # resolve without writing; exit 1 if a family is missing
```

For each family-named role the script looks, in order, in `brand/fonts/` (recursively), then in
the fonts installed on this machine (on Linux `fc-list` and the usual font folders, on macOS
`/System/Library/Fonts`, `/System/Library/Fonts/Supplemental`, `/Library/Fonts` and
`~/Library/Fonts`). It never uses the network. It matches the family name (case-insensitive),
the weight and the italic flag read from the font file, and takes the exact weight and style,
else the nearest weight of that style with a printed `WARN` naming the role, the wanted and the
got weight. A variable font becomes a static instance at the wanted weight (other axes at their
defaults). A face inside a TTC that is not face 0 is extracted to a single-face file, because
every consumer (Skia, ffmpeg `drawtext`) needs one face per file.

Where files go, and why:

- A font already in `brand/fonts/` or installed as a single-face static file is used where it is;
  installed fonts are referenced by absolute path and never copied into the project, because
  commercial licences often forbid redistribution.
- Files the script derives from fonts in `brand/fonts/` (variable-font instances, extracted TTC
  faces) go next to them, in `brand/fonts/<Family>/`.
- Files it derives from installed fonts go to `brand/fonts/.local/`.
- The result is `brand/fonts/resolved.json`: each family-named role mapped to a path (relative to
  the project root when inside it, else absolute) and the SHA-256 of the `design.json` it was
  built from. One line per role is printed: role, family, source, file.

`resolved.json` and `brand/fonts/.local/` hold machine-specific paths and are in `.gitignore`.
The loaders read `resolved.json`; if it is missing, lacks the role, was built from another
`design.json` or points at a file that is gone, they raise `FileNotFoundError` telling you to run
`uv run tools/fonts.py`. `setup.sh` runs the script, so a new machine resolves its own files
with `./setup.sh`. A font that was saved in `brand/fonts/` travels with the project; a font that
was only installed has to be installed on the new machine too.

When a family is found nowhere, the script exits 1 and names it. Either install the font on the
machine, or put its font files (TTF, OTF, TTC, or a variable font) and its licence file in
`brand/fonts/<Family>/` and rerun the script. An agent may fetch a font itself only when it has
an open licence that allows use in video (OFL, Apache); the GitHub repository `google/fonts` holds
many under `ofl/`, `apache/` and `ufl/`, with the licence file next to the fonts. It saves the
files and the licence into `brand/fonts/<Family>/`. For any other font, a human installs it or
provides the files; a commercial font is never fetched. `tools/fonts.py` is a single-file `uv`
script with one pinned dependency (fonttools).

### Who reads what

| Renderer    | Reads                                     | Where it shows                                                                                                                                                                                                 |
| ----------- | ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| motion      | fonts, all four colours, logo             | `gfx.BG`, `FG`, `FG2`, `ACCENT`; `HAIR` and `CARD` mixed from them; `gfx.typeface(weight, italic=False)`, `gfx.font(size, weight=400, italic=False)`; `logo.draw`. Alpha variants use the same colours         |
| edit        | fonts, background, text, secondary, grain | the flat background and its grain; `art.BACKGROUND`, `art.SECONDARY`, `art.rgb()`, `art.font(size, weight=400, italic=False)` for window titles, cards and placeholders; window chrome is a fixed neutral grey |
| TUI capture | mono, background, text                    | the terminal font and default colours; bold and italic synthesised, the cell size fitted to any monospace font                                                                                                 |
| web capture | nothing                                   | the product's real frontend, in its own fonts and theme                                                                                                                                                        |

Placeholders in `edit/build/placeholders/` are cached with the design they were drawn in: delete
them after changing `design.json`.

### Legibility

- **Text sizes at 1080p**: body text at least 22 px, labels 26-34 px, hero names 52-62 px. A
  share copy or a phone screen shows the same frame smaller, so stay above these.
- **Title-safe**: keep every element inside 5 % title-safe (96 px from the left and right edges,
  54 px from the top and bottom). Nothing touches a container edge.
- **Contrast**: text on the background at least 4.5:1, secondary text at least 3:1 (WCAG; the
  checker warns below these). Text over b-roll or a capture needs the same: dim or desaturate the
  plane under it (`Plane.dim`, `Plane.saturation`).
- **Cards fit their text**: size cards from measured content (`gfx.text_width`), never from a
  guess.
- **Narrated UI shots** fill at least 80 % of the frame width, tilt at most 6-10 degrees, and push
  in on what the narration names.

### Rejected styles

`NOTES.md` keeps a "Rejected styles" list. Seed it from `BRAND.md`, "Things to avoid", and add an
entry every time the human rejects a look, a motif, a transition, a sound or a delivery, before
anyone is briefed. Each entry names what was rejected, the round, the human's reason, and the
workstreams it binds:

```markdown
## Rejected styles

- From BRAND.md: <a colour, effect or motif the brand avoids>. All workstreams.
- Round 1: <the element> ("<the human's words>"). Motion and edit.
- Round 2: <an instrument, a tempo or an energy> ("<the human's words>"). Music.
```

Every brief quotes the entries for its workstream. The lead checks each preview against the list
([QA checklist](#qa-checklist-every-master)) and purges a rejected element from every agent's
work, the edit decision list included. Bring nothing back in a new form without asking. When a
rejection says something lasting about the brand, propose the change to `BRAND.md` too.

### Transitions

A `Segment` enters with a `Transition(kind, dur, direction, ease)`:

| `kind`     | What it does                                                                                  |
| ---------- | --------------------------------------------------------------------------------------------- |
| `cut`      | the new segment replaces the old at once                                                      |
| `dissolve` | a crossfade over `dur` seconds                                                                |
| `push`     | the old segment travels out along `direction` as the new one enters, with motion blur         |
| `zoom`     | the old segment scales up and fades out; the new one grows from slightly smaller and fades in |

`ease` names the curve (`quint` by default, `sine` for a gentle one). The mix adds a quiet whoosh
to `push` and `zoom` only. The background stays the same through every transition. Pick a small
set in the shared spec, give each a meaning (a push for the next step in a sequence, a dissolve
for a change of subject, say), and dissolve the credit line in.

## Editorial rules

Record the human's own rules in `NOTES.md` as they state them. These hold for any product:

- **Tone**: plain and accurate. No cheesy anthropomorphism ("watch it think"), no LLM-isms, no
  hype. State features plainly. If a third-party tool appears on screen (a coding agent's
  terminal, say), say what it is and what the product does with it.
- **Name things correctly**: never call a component by the name of what it wraps or works with;
  use real identifiers (versions, ids, commands) where the script names them; never claim a
  setting the product does not have; word a setting's scope exactly as the product does ("for
  every project, or just the one you're working on", never "for yourself"). Check every claim
  against the product's source or docs before recording it. Agree the exact wording of the pitch
  with the human and keep it fixed afterwards.
- **Name a category, never other companies** (say "frontier labs" and list no names).
- **The closing line must mean something on its own**; an approved line reused as a vague
  imperative fails.
- **No word repeated in consecutive sentences** ("Engineers... Engineers...").
- **Numbers on screen look plausible** for what they depict (token counts in the billions, not
  millions, when the scene is about brute force).
- **Licence**: mention the product's licence only if the human wants it, and read it from the
  repository's LICENSE file.
- **Credits**: only what a licence requires ([Subtitles and credits](#subtitles-and-credits)).
- **Length and runtime**: decide the length with the human (a ~1:45 trim or a ~3 min full script)
  and record it; once the human says the length is fine, stop trimming. Runtime of renders is not a
  constraint.
- **Decisions**: once the human asks the lead to stop asking, the lead decides and reports what it
  decided.

## Review and QA

### How the lead reviews without watching

Claude Code's Read tool shows images, so every sheet and crop can be looked at:

```bash
# a frame every 2 s as one image
ffmpeg -i preview.mp4 -vf "fps=1/2,scale=384:-1,tile=6x6" -frames:v 1 sheet.png
# a single frame at a moment that changed
ffmpeg -ss 26.0 -i master.mp4 -frames:v 1 frame.png
# a 200 % crop to inspect a fine defect
ffmpeg -i master.mp4 -frames:v 1 -vf "crop=600:360:950:380,scale=1200:-1" crop.png
# does a transparent clip really composite? decode the movie, not a still
ffmpeg -ss 11 -i scene_alpha.mov -f lavfi -i color=0x<background>:s=1920x1080 -filter_complex "[1][0]overlay" -frames:v 1 over.png
# loudness and true peak
ffmpeg -i master.mp4 -af ebur128=peak=true -f null - 2>&1 | rg 'I:|Peak:'
# is the end really black? (Y=16 in tv range)
ffmpeg -ss 182.2 -i master.mp4 -frames:v 1 -vf "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-" -f null -
```

The editor's own tools do the same from the edit: `render.py --contact --every 2`,
`render.py --frames <t...>`, `render.py --range A B`. Motion has `--contact` and
`--still t --over <hex>`. The listening judge (optional; it needs the API key) answers questions
about audio and video; without it, audio is reviewed by the loudness and silence measurements
([The listening judge](#the-listening-judge)).

Defects found this way before the human sees them: blocky glyphs in a blurred log, a clipped label
at the frame edge, text overflowing its card, a logo
reveal layered over text that should have gone, a double exposure where an end card dissolves over
the previous shot, a beat where a scene's frame is nearly empty. Static previews hide what motion
shows: check contact sheets across time.

### QA checklist (every master)

```bash
cd edit/out
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,r_frame_rate,color_space -of csv=p=0 intro.mp4
ffmpeg -hide_banner -nostats -i intro.mp4 -af ebur128=peak=true -f null - 2>&1 | rg 'I:|Peak:'
for t in 199.6 199.9; do ffmpeg -loglevel error -ss $t -i intro.mp4 -frames:v 1 -vf "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-" -f null - ; done   # expect YAVG=16 (use times near your end)
ffmpeg -loglevel error -y -i intro.mp4 -frames:v 1 -vf "crop=600:360:950:380,scale=1200:-1" /tmp/m.png   # 200 % crop of the first frame around a fine detail of the logo
ffmpeg -loglevel error -y -i intro.mp4 -vf "fps=1/2,scale=384:-1,tile=6x6" -frames:v 1 /tmp/sheet.png
```

Also check:

- the file's mtime is later than every upstream asset it should contain;
- frame 0 is the designed first frame;
- nothing from the rejected-styles list in `NOTES.md` anywhere ([Rejected styles](#rejected-styles));
- the logo is one of the files in `brand/logo/`, within `BRAND.md`'s clear space and minimum size;
- every diagram shows exactly the fixture story's data;
- text never overflows its card;
- motion alpha files verified by decoding the `.mov` itself (stills can hide accumulation bugs)
  and compositing over `design.json`'s `background` and over the shot it sits on in the edit;
- every claim in the narration and the on-screen text is true of the product;
- loudness -14 LUFS integrated with narration or music (a mix of sound design alone has no
  target), true peak at most -1 dBTP; the last frames at Y=16.

## Encoding

**Target format**: 1920x1080 at 60 fps, H.264 High (yuv420p, BT.709, tv range), AAC 48 kHz
stereo, -14 LUFS integrated with true peak at most -1 dBTP, faststart. Frame 0 is a designed
image; the video ends on a fade to pure black (Y=16).

### The master

`edit/render.py` pipes the compositor's frames to ffmpeg as raw RGB and muxes in `out/mix.wav`.
The full render encodes with x264 at `-crf 14` and `aq-mode=3` (adaptive quantisation that biases
bits toward dark areas), converts to tv-range BT.709 4:2:0, tags the stream as BT.709, and adds
320 kb/s AAC at 48 kHz. `--preview` renders, and full renders with `--fast`, swap the video
encoder for a faster one: `h264_nvenc -preset p5 -cq 20` on Linux when a test encode shows NVENC
works, `h264_videotoolbox -b:v 20M` on macOS, `libx264 -preset veryfast -crf 20` otherwise.

```bash
# the full render, as run from edit/; render.py also trims the audio input to the rendered range (-ss/-t)
ffmpeg -v error -y -f rawvideo -pix_fmt rgb24 -s 1920x1080 -r 60 -i - \
  -i out/mix.wav \
  -vf "scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv" \
  -c:v libx264 -profile:v high -preset slow -crf 14 -x264-params aq-mode=3 \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv \
  -map 0:v -map 1:a -c:a aac -b:a 320k -ar 48000 -shortest \
  -movflags +faststart out/intro.mp4
```

### The share copy

For social media and messaging, a second encode makes a smaller copy of the master. It keeps
1920x1080, drops the frame rate from 60 to 30 fps (the `fps=30` filter takes every other frame),
and uses H.264 High Profile, Level 4.1, 8-bit 4:2:0 video with AAC-LC stereo audio in an MP4
container, which Apple devices play. `-crf 21` sets visual quality rather than a fixed bitrate;
`+faststart` moves the MP4 index to the front so web playback starts promptly; `-n` refuses to
overwrite an existing output (remove it, or pick a new name, to regenerate). Run from the project
root:

```bash
ffmpeg -hide_banner -loglevel error -stats -nostdin -n \
  -i edit/out/intro.mp4 \
  -map 0:v:0 -map 0:a:0 -map_metadata 0 \
  -vf fps=30 \
  -c:v libx264 -preset slow -crf 21 \
  -profile:v high -level:v 4.1 -pix_fmt yuv420p \
  -c:a aac -b:a 160k \
  -movflags +faststart \
  edit/out/intro-share.mp4
```

Measured on one 205.9 s master:

| Property            | Share copy                                           |
| ------------------- | ---------------------------------------------------- |
| Duration            | 205.888 s                                            |
| Frame size and rate | 1920x1080, 30 fps                                    |
| Video               | H.264 High, Level 4.1, `yuv420p`, about 2.41 Mb/s    |
| Audio               | AAC-LC, 48 kHz stereo, nominal 160 kb/s              |
| Container           | MP4 with `+faststart`                                |
| File size           | 66.7 MB, about 90.5 % smaller than the 704 MB master |

A full decode of the share copy completed without errors.

## Project records

A video project keeps three files beside the pipeline. The kit ships none of them; the lead
creates them.

### `NOTES.md`: the decision log

Every human decision and correction, appended in order, written before anyone is briefed and
binding for every agent. One bullet per decision: what the human asked for (paraphrased, or the
exact wording when the words themselves are the decision, as for a script line), the rule that
follows, and what changed. Mark rejections so nobody brings them back, and confirmations so
nobody asks again. Prefix review notes with their round. Rejected looks, motifs, sounds and
deliveries also go in its "Rejected styles" list ([Rejected styles](#rejected-styles)), and every
patch to an engine file is recorded with the file and the reason, so a kit update can re-apply it
([How the kit is used](#how-the-kit-is-used)).

```markdown
# Production notes

- Voice: <Voice>, model gemini-3.8-flash-tts. Style "warm and engaged, natural conversational
  pace, quietly confident"; per-section modifiers stay small. Hushed and slow takes were rejected.
- Pitch wording (fixed): "<exact approved line>".
- REJECTED: the <motif> logo animation (colours, motion and concept). No <motif> anywhere.
  Chosen: <the approved reveal>; it is the unifying motif. Added to "Rejected styles".
- Round 2: the first frame must not be black; remove <an element>; end on a fade to black.
- Engine patch: edit/editkit/<file>.py, <what changed and why>. Re-apply after a kit update.
- Round 3: replace only the opening beat of the pitch scene; leave the rest of the scene and the
  cut unchanged.
- Credits show only what a licence requires (CC BY samples); no narration row in edit/credits.json.
```

### `edit/ISSUES.md`: the editor's issue log

Asset, problem, what the edit needs. Status is re-checked on every render; `render.py` prints any
key still on a placeholder. One bullet per issue: the asset and what is wrong in bold, then what
the edit needs and who was asked.

```markdown
# Editor issues (asset, problem, what the edit needs)

## Open

- **motion `sNN_name_alpha.mov` (time stamp): alpha nearly opaque over the whole frame with white
  RGB**, so the scene composites as a white frame. Asked motion to re-render (ground alpha 0). The
  preview for the lead is held on it.
- **unused captures:** list captures that exist but the cut does not use, and why.

## Resolved

- music: soundtrack and stems match the current grid (duration); note any stale stem that is ignored.
- a fact in a scene was confirmed correct by the lead (record it so it is not asked again).
- web manifest delivered: marks and cursor tracks are wired (list each clip and its mark).
- a rejected motif was removed from the edit (list the transitions and elements that replaced it).
```

### `HANDBOOK.md`: the project's own handbook

Lets the next agent pick the project up cold. Paths are relative to the project root. Sections:

- **Status**: which review round is done, what is open, which assets exist but are unused.
- **Target format and output names.**
- **The fixture story**: the table and its rules.
- **The timeline**: one row per scene, from `timeline.json`, as below.
- **Brand**: written by the brand skill, one part per workstream (narration voice and tone, music
  feel, motion, captures, edit). Rerun the skill rather than editing it by hand.
- **The design system** as data ([Defining the design](#defining-the-design)), and the
  **editorial rules** the human has stated.
- **Per-workstream tables**: motion scenes (name, window, duration, content), web clips (length,
  key marks), TUI clips (size, key times), b-roll picks, the score's tempo, grid and arc.
- **Commands** that differ from this README.
- **Review rounds**: one line per round, what the human asked for and what changed. Decisions with
  their reasons stay in `NOTES.md`; defects in `edit/ISSUES.md`.

| Scene key | Start | Narration window | Narration text           | Picture                                                                                                              |
| --------- | ----- | ---------------- | ------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| open      | 0.0   | `<start>-<end>`  | the problem statement    | first-frame hold with a fade, a motion scene on its own ground, b-roll for the last beat, the logo reveal from `<t>` |
| (insert)  | n/a   | `<start>-<end>`  | "Introducing <product>." | during the logo reveal, once the logo is settled                                                                     |
| pitch     | `<t>` | `<start>-<end>`  | what the product is      | a motion scene                                                                                                       |
| ...       |       |                  |                          | one row per scene: capture clips, motion scenes, insets and the marks they sync to                                   |
| close     | `<t>` | `<start>-<end>`  | tagline, licence line    | the last capture dissolves to the end card                                                                           |
| credits   | `<t>` | n/a              | n/a                      | one subtle centred line on the background; fade to black; pure black hold                                            |

## Mistakes and pitfalls

| Area      | What went wrong                                                                                                                 | Rule                                                                                                   |
| --------- | ------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Brief     | The lead redirected the composer toward the wrong genre, misreading a music reference the human gave                            | Ask what a reference means to this person, or offer short excerpts early                               |
| Narration | A hushed, then a bored, then an eager narrator                                                                                  | Audition a few directions on the same lines and let the human pick; keep style directions short        |
| Narration | TTS read `<short pause>` aloud, dropped words, added vocal fry                                                                  | Render 2-3 takes and judge each against the expected text                                              |
| Narration | A sentence spliced into an approved take was audible                                                                            | Use one take whole                                                                                     |
| Narration | A re-take of an early line would have shifted every later scene                                                                 | Give later sections a `pin` in `sections.json`                                                         |
| Narration | The TTS client was garbage-collected mid-request                                                                                | Keep `client = genai.Client()` in a local variable                                                     |
| Narration | The free tier's 10 TTS requests a day ran out during auditions                                                                  | Enable billing; batch auditions                                                                        |
| Script    | Cheesy or inaccurate lines (anthropomorphism, a setting the product does not have, a component called by the wrong name)        | Check every claim against the product's source or docs before recording                                |
| Judge     | Scores drifted between identical calls; it heard voiceovers in instrumentals                                                    | Use it for direction and A/B comparisons, never single-call pass or fail                               |
| Music     | A new sustained layer entering on the logo reveal was rejected                                                                  | Let the hook and the pulse carry an arrival                                                            |
| Review    | A preview containing an already-rejected animation reached the human (the edit still referenced it)                             | The lead reviews every preview first; purge rejected elements from every agent's work                  |
| Review    | A b-roll agent's "no logos" claim missed two branded clips                                                                      | The lead checks every contact sheet itself                                                             |
| Review    | Card and node text overflowed its card in a pull-back graph                                                                     | Size cards from measured content                                                                       |
| Team      | Messages crossed: agents reported on an old brief while a newer one sat in their inbox                                          | Check whether the agent is running or idle and look at file timestamps before re-sending               |
| Team      | A watcher loop that searched for another agent's process matched its own command line and never ended                           | Wait on files or explicit messages                                                                     |
| Files     | A capture overwritten in place was read half-written by the editor                                                              | Write to a temporary name and rename atomically; signal "final" explicitly                             |
| Fixtures  | A redundant dependency edge in the fixture story, found after capture                                                           | Review the fixture data for sense before capturing anything                                            |
| Fixtures  | A tmux socket under a long fixture path could not be created (Unix socket paths hold about 104-108 bytes)                       | Keep `TMUX_TMPDIR` short; `tmux_server` refuses a longer path                                          |
| Motion    | Stills looked right but the encoded transparent movie was opaque white (GL blending left on by skia, framebuffer never cleared) | `fbo.clear()` and disable blending before every shader pass; verify transparency by decoding the movie |
| Motion    | `GrDirectContext.MakeGL()` returned `None` under moderngl's EGL context on Linux                                                | `GrDirectContext.MakeGL(skia.GrGLInterface.MakeEGL())` on Linux; `MakeGL()` on macOS                   |
| Motion    | Blocky text from 8-bit accumulation of a temporal blur                                                                          | Accumulate in half-float (RGBA F16) render targets                                                     |
| Edit      | A background-replacement step in the edit drew a smudge on the logo in the first frame                                          | Render the asset at the source instead of repairing it downstream                                      |
| Edit      | Grain and dither added after the fade kept black frames above Y=16                                                              | Fade them with the picture; check with `signalstats`                                                   |
| Edit      | Untagged motion clips decoded with the wrong matrix                                                                             | Decode untagged H.264 as BT.601                                                                        |
| Credits   | A credits card held for 11 s for a single credit                                                                                | One subtle line, about 5 s with the fade                                                               |
| B-roll    | Veo output and CC BY stock were rejected as poor or off-message                                                                 | Generate with Gemini Omni                                                                              |
| B-roll    | An outdated `yt-dlp` only got 360p streams                                                                                      | Upgrade it before searching                                                                            |

## Snippets

The listening judge (`tools/listen.py`), in essence:

```python
from google import genai

client = genai.Client()
parts = []
for path in files:
    uploaded = client.files.upload(file=path)
    parts += [f"File: {path}", uploaded]
parts.append(question)
print(client.models.generate_content(model="gemini-3.5-flash", contents=parts).text)
```

Finding pauses in a take, to cut a sentence without re-recording:

```bash
ffmpeg -i take.wav -af silencedetect=noise=-40dB:d=0.25 -f null - 2>&1 | rg -o 'silence_(start|end): [0-9.]+'
ffmpeg -i take.wav -af "atrim=0:20.35,afade=t=out:st=20.15:d=0.2" take_trim.wav
```

Deterministic browser capture, in outline:

```python
for frame in range(n_frames):
    t = frame / 60
    world.tick(t)                          # the mock server's clock drives every status frame and terminal byte
    await page.clock.run_for(1000 / 60)    # the page's timers advance by exactly one frame
    await seek_css_animations(page, t)     # every CSS animation set to the same instant
    await page.screenshot(path=f"frames/{frame:06d}.png")
```

Terminal rendering, in outline:

```python
import pyte, ptyprocess

screen = pyte.Screen(120, 34)
stream = pyte.ByteStream(screen)
proc = ptyprocess.PtyProcess.spawn(["<product>", "<command>"], dimensions=(34, 120))
while proc.isalive():
    stream.feed(proc.read(65536))
    snapshot(screen.buffer, t=now())       # later drawn frame by frame with skia in the mono font
```

## Licences and credits

- **Music samples**: Salamander Grand Piano V3 (Alexander Holm, CC BY 3.0, credited on screen) and
  VSCO 2 Community Edition (Versilian Studios, CC0 1.0, no attribution needed), downloaded by
  `setup.sh` unless it runs with `--no-samples`. `music/CREDITS.md` records sources, files, licences and which instruments each
  library supplies; everything else in the score is synthesized.
- **B-roll**: generated with Gemini Omni; no attribution required. `broll/CREDITS.md` states this
  and holds a section for any CC BY clip added later.
- **Fonts**: the project's own, in `brand/fonts/` with their licences; `BRAND.md`, "Legal", says
  whether each allows use in video and asks for credit. Where `design.json` names none, the
  renderers use the system fonts (DejaVu Sans and DejaVu Sans Mono on Linux, Helvetica and Menlo
  on macOS); the kit ships no font.
- **Logo and brand assets**: the product owner's, in `brand/`; show trademark lines as `BRAND.md`,
  "Legal", asks.
- **Narration**: Gemini TTS; no on-screen attribution.
- **Your product**: state its licence in the closing line only if the human wants it.
