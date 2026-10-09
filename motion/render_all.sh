#!/usr/bin/env bash
# Renders every scene listed in scenes.txt, each with 0.5 s handles on both ends, as its
# default plus the transparent variant when the default is opaque (render.py --variants).
# scenes.txt: one scene per line, the module name in scenes/ followed by any render.py
# arguments (usually --duration <window from narration/timeline.json>); # starts a comment.
# Usage: ./render_all.sh  (from motion/)
set -euo pipefail
cd "$(dirname "$0")"
H=0.5
if [ ! -f scenes.txt ]; then
  echo "no scenes.txt: list the scenes to render, one per line (README.md, \"Motion graphics\")" >&2
  exit 1
fi
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%%#*}"
  # shellcheck disable=SC2086  # the line's words are the scene name and its arguments
  set -- $line
  [ "$#" -gt 0 ] || continue
  uv run python render.py "$@" --variants --handle "$H" < /dev/null 2> >(grep -v Fontconfig >&2)
done < scenes.txt
echo ALL DONE
