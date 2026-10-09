#!/usr/bin/env bash
# Prepare a fresh Linux or macOS machine for this kit. Needs no administrator rights and never uses sudo;
# system packages come from ./system-deps.sh, which a person runs in their own terminal.
#   ./setup.sh                install and fetch everything missing
#   ./setup.sh --no-samples   the same, without the music sample libraries
#   ./setup.sh --check        only report
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

CHECK=0
WANT_SAMPLES=1
for arg in "$@"; do
  case "$arg" in
    --check) CHECK=1 ;;
    --no-samples) WANT_SAMPLES=0 ;;
    -h|--help)
      cat <<'EOF'
Usage: ./setup.sh [--check] [--no-samples]

  (no flag)     install Python environments, the Claude Code skills (narration,
                brand; into .claude/skills/ of this project), sample libraries
                (about 3.4 GB download), Chromium and the Whisper model
  --no-samples  skip the sample libraries: a video without music, or with a
                score of synthesized instruments only, does not need them
  --check       report what is ready and what is missing; change nothing

Exit status is 1 if anything required is MISSING, else 0. The Gemini API key,
the sample libraries and the Whisper model are optional (WARN).
EOF
      exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

MISSING=0
WARNED=0
OS="$(uname -s)"
SAMPLES="$ROOT/music/samples"
SKILLS_DST="$ROOT/.claude/skills"
KIT_SKILLS="brand narration" # the skills install.sh copies; checked where claude-skills/ is absent

# status LEVEL ITEM [HINT]: one line per item, counts WARN and MISSING
status() {
  case "$1" in
    MISSING) MISSING=$((MISSING + 1)) ;;
    WARN) WARNED=$((WARNED + 1)) ;;
  esac
  printf '%-9s %-22s %s\n' "$1" "$2" "${3:-}"
}

section() { printf '\n== %s ==\n' "$1"; }

# SYSDEPS: where a missing system package comes from. This script never uses sudo.
SYSDEPS="run ./system-deps.sh in a terminal outside Claude Code (or ask an administrator)"

check_cmd() { # check_cmd CMD LEVEL HINT
  if command -v "$1" >/dev/null 2>&1; then status ok "$1"; else status "$2" "$1" "$3"; fi
}

check_commands() {
  section "Commands"
  check_cmd uv MISSING "$SYSDEPS"
  check_cmd ffmpeg MISSING "$SYSDEPS"
  check_cmd ffprobe MISSING "$SYSDEPS"
  check_cmd curl MISSING "$SYSDEPS"
  check_cmd tar MISSING "$SYSDEPS"
  # macOS tar unpacks .tar.xz without the xz command
  if [ "$OS" != Darwin ]; then check_cmd xz MISSING "$SYSDEPS"; fi
  check_cmd unzip MISSING "$SYSDEPS"
  check_cmd rg WARN "$SYSDEPS (search commands in README.md)"
  check_cmd tmux WARN "$SYSDEPS (terminal captures only)"
  check_cmd claude WARN "curl -fsSL https://claude.ai/install.sh | bash (Claude Code CLI)"
  if command -v ffmpeg >/dev/null 2>&1; then
    local enc hw=h264_nvenc
    enc="$(ffmpeg -hide_banner -encoders 2>/dev/null || true)"
    for e in libx264 prores_ks aac; do
      if grep -qw "$e" <<<"$enc"; then status ok "ffmpeg encoder $e"
      else status MISSING "ffmpeg encoder $e" "install an ffmpeg build with $e: $SYSDEPS"; fi
    done
    if [ "$OS" = Darwin ]; then hw=h264_videotoolbox; fi
    # a build can list h264_nvenc on a machine without an NVIDIA driver: test an encode
    if grep -qw "$hw" <<<"$enc" && ffmpeg -v error -nostdin -f lavfi -i testsrc2=s=256x144:d=0.2 -c:v "$hw" -f null - >/dev/null 2>&1
    then status ok "ffmpeg encoder $hw"
    else status WARN "ffmpeg encoder $hw" "not usable here; edit previews and placeholders use libx264 (slower)"; fi
  fi
}

sync_envs() {
  section "Python environments"
  local d
  for d in edit motion music fixtures/web fixtures/tui; do
    if [ -d "$ROOT/$d/.venv" ]; then
      status ok "$d"
    elif [ "$CHECK" = 1 ]; then
      status MISSING "$d" "run ./setup.sh"
    elif ! command -v uv >/dev/null 2>&1; then
      status MISSING "$d" "install uv first"
    elif (cd "$ROOT/$d" && uv sync --frozen); then
      status installed "$d"
    else
      status MISSING "$d" "uv sync --frozen failed in $d"
    fi
  done
}

# gpu_probe ITEM DIR CODE: open a workstream's own GL context with its environment.
# A software renderer (Mesa llvmpipe or softpipe, Apple Software Renderer) works, on the CPU.
gpu_probe() {
  local py="$ROOT/$2/.venv/bin/python" out renderer hint
  if [ ! -x "$py" ]; then status MISSING "$1" "run ./setup.sh first"; return; fi
  if [ "$OS" = Darwin ]; then hint="the CGL context (OpenGL 4.1, part of macOS) did not open"
  else hint="needs OpenGL 4.1 through headless EGL: a GPU driver, or Mesa for CPU rendering: $SYSDEPS"; fi
  if out="$(cd "$ROOT/$2" && "$py" -c "$3" 2>&1)"; then
    renderer="$(tail -n 1 <<<"$out")"
    case "$renderer" in
      *llvmpipe*|*softpipe*|*"Software Rasterizer"*|*"Software Renderer"*)
        status WARN "$1" "$renderer: CPU rendering: much slower (README.md, \"Requirements\")" ;;
      *) status ok "$1" "$renderer" ;;
    esac
  else
    status MISSING "$1" "$hint; error: $(tail -n 1 <<<"$out")"
  fi
}

check_gpu() {
  section "GPU (OpenGL)"
  gpu_probe "edit compositor" edit 'from editkit.gpu import GPU; print(GPU().ctx.info["GL_RENDERER"])'
  gpu_probe "motion graphics" motion 'from lib.gfx import Gpu; print(Gpu().ctx.info["GL_RENDERER"])'
}

# check_design: design.json is optional; when present, the motion loader checks its keys,
# colours and font paths (README.md, "Design system")
check_design() {
  local py="$ROOT/motion/.venv/bin/python" out
  if [ ! -f "$ROOT/design.json" ]; then status ok "design.json" "absent: system fonts and neutral colours in use"
  elif [ ! -x "$py" ]; then status WARN "design.json" "run ./setup.sh first to check it"
  elif out="$(cd "$ROOT/motion" && "$py" -c 'from lib import design; design.load(); design.font(); design.mono()' 2>&1)"
  then status ok "design.json" "fonts and colours valid"
  else status MISSING "design.json" "$(tail -n 1 <<<"$out")"; fi
}

# check_families: fonts that design.json names by family; tools/fonts.py finds the files
# (brand/fonts/, then the installed fonts) and writes brand/fonts/resolved.json
check_families() {
  local out flag="" line n
  if [ ! -f "$ROOT/design.json" ] || [ ! -f "$ROOT/tools/fonts.py" ]; then return; fi
  if ! command -v uv >/dev/null 2>&1; then return; fi
  if [ "$CHECK" = 1 ]; then flag="--check"; fi
  if out="$(cd "$ROOT" && uv run tools/fonts.py ${flag:+"$flag"} 2>&1)"; then
    case "$out" in "nothing to resolve"*) return ;; esac
    line="$(grep -m1 '^WARN' <<<"$out" || true)"
    n="$(grep -c '^fonts\.' <<<"$out" || true)"
    if [ -n "$line" ]; then status WARN "font families" "${line#WARN }"
    else status ok "font families" "$n resolved"; fi
  else
    line="$(grep -m1 '^MISSING' <<<"$out" || true)"
    status MISSING "font families" "${line:-$(tail -n 1 <<<"$out")}"
  fi
}

# check_system_fonts: the fonts used for any role design.json leaves unnamed
check_system_fonts() {
  local f found=1
  if [ "$OS" = Darwin ]; then
    for f in Helvetica.ttc Menlo.ttc; do [ -f "/System/Library/Fonts/$f" ] || found=0; done
    if [ "$found" = 1 ]; then status ok "system fonts" "Helvetica, Menlo"
    else status WARN "system fonts" "Helvetica.ttc or Menlo.ttc not in /System/Library/Fonts (they ship with macOS)"; fi
    return
  fi
  for f in "DejaVu Sans" "DejaVu Sans Mono"; do
    if command -v fc-match >/dev/null 2>&1; then
      case "$(fc-match -f '%{family}' "$f" 2>/dev/null)" in "$f"|"$f",*) ;; *) found=0 ;; esac
    else
      [ -f "/usr/share/fonts/truetype/dejavu/$(tr -d ' ' <<<"$f").ttf" ] || found=0
    fi
  done
  if [ "$found" = 1 ]; then status ok "system fonts" "DejaVu Sans, DejaVu Sans Mono"
  else status WARN "system fonts" "DejaVu Sans not found (used where design.json names no font): $SYSDEPS"; fi
}

check_fonts() {
  section "Fonts"
  check_families
  check_design
  check_system_fonts
  local f missing=0 hint
  if [ "$OS" = Darwin ]; then
    for f in Menlo.ttc "Apple Symbols.ttf" "Apple Color Emoji.ttc"; do
      [ -f "/System/Library/Fonts/$f" ] || missing=1
    done
    hint="Menlo, Apple Symbols or Apple Color Emoji not in /System/Library/Fonts (terminal captures only)"
  else
    for f in dejavu/DejaVuSansMono.ttf noto/NotoSansSymbols2-Regular.ttf noto/NotoSansSymbols-Regular.ttf \
             noto/NotoSansMath-Regular.ttf noto/NotoColorEmoji.ttf; do
      [ -f "/usr/share/fonts/truetype/$f" ] || missing=1
    done
    hint="$SYSDEPS (terminal captures only)"
  fi
  if [ "$missing" = 0 ]; then status ok "fallback fonts"; else status WARN "fallback fonts" "$hint"; fi
}

# install_skill NAME: copy claude-skills/NAME/ into .claude/skills/NAME/ unless a copy is there
install_skill() {
  local src="$ROOT/claude-skills/$1" dst="$SKILLS_DST/$1" d line
  if [ ! -d "$src" ]; then # a project made by install.sh keeps only the installed copy
    if [ -f "$dst/SKILL.md" ]; then status ok "$1 skill"
    else status MISSING "$1 skill" "$dst/SKILL.md not found; rerun install.sh from the kit"; fi
  elif [ ! -e "$dst" ]; then
    if [ "$CHECK" = 1 ]; then status MISSING "$1 skill" "run ./setup.sh"; return; fi
    mkdir -p "$SKILLS_DST"
    cp -R "$src" "$dst"
    status installed "$1 skill" "$dst"
  elif d="$(diff -rq "$src" "$dst")"; then
    status ok "$1 skill"
  else
    status WARN "$1 skill" "$dst differs from the kit copy; not overwritten"
    while IFS= read -r line; do printf '            %s\n' "$line"; done <<<"$d"
  fi
}

# install_skills: the kit's skills, from claude-skills/ in the kit, else the ones install.sh copied
install_skills() {
  section "Claude Code skills"
  local d names="$KIT_SKILLS"
  if [ -d "$ROOT/claude-skills" ]; then
    names=""
    for d in "$ROOT"/claude-skills/*/; do
      case "$d" in */__pycache__/|*"/*/") ;; *) d="${d%/}"; names="$names ${d##*/}" ;; esac
    done
  fi
  for d in $names; do install_skill "$d"; done
}

# brand_newer: files in BRAND.md and brand/ changed after design.json, relative to the project root
brand_newer() {
  if [ -e "$ROOT/BRAND.md" ] || [ -d "$ROOT/brand" ]; then
    (cd "$ROOT" && find BRAND.md brand -type f -newer design.json 2>/dev/null || true)
  fi
}

# check_brand: BRAND.md and brand/ are optional; the brand skill generates design.json from them
# (README.md, "Brand")
check_brand() {
  section "Brand"
  local py="$ROOT/motion/.venv/bin/python" newer out
  if [ -f "$ROOT/BRAND.md" ]; then status ok "BRAND.md"
  else status WARN "BRAND.md" "optional: run the brand skill in Claude Code to create it"; fi
  [ -f "$ROOT/design.json" ] || return 0
  newer="$(brand_newer)"
  if [ -n "$newer" ]; then
    status WARN "design.json" "older than $(head -n 1 <<<"$newer"): rerun the brand skill"
  fi
  grep -q '"logo"' "$ROOT/design.json" || return 0
  if [ ! -x "$py" ]; then status WARN "logo" "run ./setup.sh first to check it"
  elif out="$(cd "$ROOT/motion" && "$py" -c 'from lib import design; print(design.logo())' 2>&1)"
  then status ok "logo" "${out#"$ROOT"/}"
  else status MISSING "logo" "$(tail -n 1 <<<"$out")"; fi
}

# fetch_archive URL DEST_ARCHIVE: resumable download, renamed only when complete. Some hosts (GitHub's
# generated zips) ignore Range requests, so a failed resume discards the .part file and retries once.
fetch_archive() {
  [ -f "$2" ] && return 0
  if ! curl -fL --retry 3 -C - -o "$2.part" "$1"; then
    rm -f "$2.part"
    curl -fL --retry 3 -o "$2.part" "$1" || { rm -f "$2.part"; return 1; }
  fi
  mv "$2.part" "$2"
}

# warn_disk_space: once, before the first download, if under 10 GB is free
DISK_WARNED=0
warn_disk_space() {
  [ "$DISK_WARNED" = 0 ] || return 0
  DISK_WARNED=1
  local free_kb
  free_kb="$(df -Pk "$ROOT/music" | tail -n 1 | tr -s ' ' | cut -d' ' -f4)"
  if [ "${free_kb:-0}" -lt 10485760 ]; then
    status WARN "disk space" "under 10 GB free in $SAMPLES; archives plus unpacked files need about 9 GB"
  fi
}

# unpack ARCHIVE KIND TOPDIR: extract to a temp dir, then move the top folder into place.
# Every step is chained: errexit is off inside an `if` condition, so a failed extract must not reach the mv.
unpack() {
  local archive="$1" kind="$2" top="$3" tmp="$SAMPLES/.extract-$3"
  rm -rf "$tmp" && mkdir -p "$tmp" || return 1
  if [ "$kind" = zip ]; then unzip -q "$archive" -d "$tmp" || return 1
  else tar -xJf "$archive" -C "$tmp" || return 1; fi
  rm -rf "${SAMPLES:?}/$top" && mv "$tmp/$top" "$SAMPLES/$top" && rm -rf "$tmp" "$archive"
}

# sample_set NAME KIND TOPDIR SIZE URL DONE_PATH...: one library, complete when every DONE_PATH exists
sample_set() {
  local name="$1" kind="$2" top="$3" size="$4" url="$5" p; shift 5
  local archive="$SAMPLES/$top.$kind"
  [ "$kind" = zip ] || archive="$SAMPLES/$top.tar.xz"
  local done=1
  for p in "$@"; do [ -e "$SAMPLES/$p" ] || done=0; done
  if [ "$done" = 1 ]; then status ok "$name"; return; fi
  if [ "$CHECK" = 1 ]; then status WARN "$name" "music with sampled instruments only; ./setup.sh downloads it (about $size)"; return; fi
  if [ "$WANT_SAMPLES" = 0 ]; then status WARN "$name" "skipped (--no-samples): music with sampled instruments only"; return; fi
  warn_disk_space
  echo "          downloading $name (about $size) ..."
  if ! fetch_archive "$url" "$archive"; then
    status WARN "$name" "download failed; rerun ./setup.sh to resume ($url)"
  elif unpack "$archive" "$kind" "$top"; then
    status fetched "$name"
  else
    rm -rf "$archive" "$SAMPLES/.extract-$top"
    status WARN "$name" "archive did not unpack; rerun ./setup.sh to download it again"
  fi
}

# fetch_samples: optional; only a score with sampled instruments (piano, strings, mallets, brass) needs them
fetch_samples() {
  section "Sample libraries"
  if [ "$CHECK" = 0 ] && [ "$WANT_SAMPLES" = 1 ]; then mkdir -p "$SAMPLES"; fi
  sample_set "Salamander piano" tar SalamanderGrandPianoV3_48khz24bit "1.2 GB" \
    "https://freepats.zenvoid.org/Piano/SalamanderGrandPiano/SalamanderGrandPianoV3+20161209_48khz24bit.tar.xz" \
    SalamanderGrandPianoV3_48khz24bit/SalamanderGrandPianoV3Retuned.sfz SalamanderGrandPianoV3_48khz24bit/48khz24bit
  sample_set "VSCO-2 CE" zip VSCO-2-CE-master "2.2 GB" \
    "https://github.com/sgossner/VSCO-2-CE/archive/refs/heads/master.zip" \
    VSCO-2-CE-master/Brass
}

chromium_path() {
  (cd "$ROOT/fixtures/web" && .venv/bin/python -c '
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
print(p.chromium.executable_path)
p.stop()' 2>/dev/null | tail -n 1) || true
}

check_chromium() {
  section "Chromium (web capture)"
  if [ ! -x "$ROOT/fixtures/web/.venv/bin/python" ]; then status WARN chromium "run ./setup.sh first"; return; fi
  local exe hint=""
  if [ "$OS" != Darwin ]; then hint="if Chromium fails to start: $SYSDEPS"; fi
  exe="$(chromium_path)"
  if [ -n "$exe" ] && [ -x "$exe" ]; then status ok chromium; return; fi
  if [ "$CHECK" = 1 ]; then status WARN chromium "run ./setup.sh (web captures only)"; return; fi
  if (cd "$ROOT/fixtures/web" && uv run --frozen playwright install chromium); then
    status installed chromium "$hint"
  else
    status WARN chromium "playwright install failed; web captures only"
  fi
}

whisper_model() { # model name as loaded by edit/words.py
  grep -o 'WhisperModel("[^"]*"' "$ROOT/edit/words.py" | head -n 1 | cut -d'"' -f2 || true
}

check_whisper() {
  section "Whisper model"
  local model cache
  model="$(whisper_model)"
  if [ -z "$model" ]; then status WARN whisper "model name not found in edit/words.py"; return; fi
  cache="${HF_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/huggingface}/hub/models--${model//\//--}"
  if [ -d "$cache/snapshots" ] && [ -n "$(find "$cache/snapshots" -name model.bin 2>/dev/null | head -n 1)" ]; then
    status ok "$model"
  elif [ "$CHECK" = 1 ] || [ ! -x "$ROOT/edit/.venv/bin/python" ]; then
    status WARN "$model" "word timings for narration only; downloads on first run (or run ./setup.sh)"
  elif (cd "$ROOT/edit" && .venv/bin/python -c "import faster_whisper; faster_whisper.download_model('$model')" >/dev/null); then
    status fetched "$model"
  else
    status WARN "$model" "download failed; it will download on first run"
  fi
}

check_api_key() {
  section "API key"
  if [ -n "${GEMINI_API_KEY:-}${GOOGLE_API_KEY:-}" ]; then
    status ok "Gemini API key"
  else
    status WARN "Gemini API key" "optional: only a narrated voice (TTS), generated b-roll (tools/genvideo.py) and the listening judge (tools/listen.py) call Gemini; without it the lead reviews audio with ffmpeg measurements only. For them, create a key at https://aistudio.google.com/apikey and: export GEMINI_API_KEY=...  Enable billing: the free tier allows only 10 TTS requests a day."
  fi
}

main() {
  if [ "$CHECK" = 1 ]; then echo "Check only: nothing will be changed."; fi
  case "$OS" in
    Linux|Darwin) ;;
    *) status WARN platform "$OS: this kit runs on Linux and macOS; continuing" ;;
  esac
  check_commands
  sync_envs
  check_gpu
  check_fonts
  check_brand
  install_skills
  fetch_samples
  check_chromium
  check_whisper
  check_api_key
  printf '\nSummary: %d MISSING, %d WARN\n' "$MISSING" "$WARNED"
  if [ "$MISSING" -gt 0 ]; then
    echo "Fix the MISSING items above, then rerun ./setup.sh"
    exit 1
  fi
}

# run unless sourced (sourcing lets a test call single functions)
if [ "${BASH_SOURCE[0]}" = "$0" ]; then main; fi
