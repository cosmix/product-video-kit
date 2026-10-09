#!/usr/bin/env bash
# Rebuild final/ from the chosen takes in sources.json: trim ends, cap pauses at 0.45 s, tempo +4%.
# sources.json maps a section name to one take, or a list of two joined with 0.5 s of silence.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p final
F="silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.03,silenceremove=stop_periods=-1:stop_threshold=-45dB:stop_duration=0.45:stop_silence=0.45,areverse,silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.08,areverse,atempo=1.04,aresample=48000"
takes="$(uv run --quiet build_timeline.py --sources)"
while read -r name a b; do
  [ -n "$name" ] || continue
  if [ -n "${b:-}" ]; then
    ffmpeg -nostdin -hide_banner -loglevel error -y -i "$a" -f lavfi -t 0.5 -i anullsrc=r=24000:cl=mono -i "$b" -filter_complex "[0:a]aresample=24000,aformat=channel_layouts=mono[x];[1:a]aformat=channel_layouts=mono[y];[2:a]aresample=24000,aformat=channel_layouts=mono[z];[x][y][z]concat=n=3:v=0:a=1,$F" -c:a pcm_s24le "final/$name.wav"
  else
    ffmpeg -nostdin -hide_banner -loglevel error -y -i "$a" -af "$F" -c:a pcm_s24le "final/$name.wav"
  fi
done <<<"$takes"
