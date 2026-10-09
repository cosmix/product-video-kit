# /// script
# dependencies = ["google-genai"]
# ///
"""Generate b-roll clips with Gemini Omni from broll/gen/shots.json.

usage: uv run tools/genvideo.py [--only <id>]
Outputs broll/gen/omni/<id>.mp4 and <id>.json (skips ids already present).
Logs every attempt's token counts and clip length to usage.jsonl (tools/usage_log.py).
"""
import argparse
import base64
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from google import genai

import usage_log

ROOT = Path(__file__).resolve().parent.parent / "broll" / "gen"
MODEL = "gemini-omni-1.1-flash"
OMNI_FMT = {"type": "video", "aspect_ratio": "16:9", "resolution": "1080p", "delivery": "inline"}


def slim(obj):
    """Drop large blobs (base64 video) so metadata stays readable."""
    if isinstance(obj, dict):
        return {k: slim(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [slim(v) for v in obj]
    return "<blob>" if isinstance(obj, str) and len(obj) > 2000 else obj


def seconds(path):
    """Clip length from ffprobe, or None when it cannot be read."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                        str(path)], capture_output=True, text=True)
    try:
        return round(float(r.stdout), 2)
    except ValueError:
        return None


def omni(client, prompt, out, sid):
    r = client.interactions.create(model=MODEL, input=prompt, response_modalities=["video"],
                                   response_format=OMNI_FMT)
    vid = r.output_video
    usage = usage_log.from_interaction(r.usage)
    if vid is None or not (vid.data or vid.uri):
        usage_log.log("genvideo", MODEL, usage, shot=sid, ok=False)
        raise RuntimeError(f"no video returned: {slim(r.model_dump(mode='json', exclude_none=True))}")
    if vid.data:
        Path(out).write_bytes(vid.data if isinstance(vid.data, bytes) else base64.b64decode(vid.data))
    else:
        usage_log.log("genvideo", MODEL, usage, shot=sid, ok=False)
        raise RuntimeError(f"uri delivery not handled: {vid.uri}")
    usage_log.log("genvideo", MODEL, usage, shot=sid, ok=True, seconds=seconds(out))
    return OMNI_FMT, {"interaction": slim(r.model_dump(mode="json", exclude_none=True))}


def run(client, shot):
    d = ROOT / "omni"
    d.mkdir(parents=True, exist_ok=True)
    final = d / f"{shot['id']}.mp4"
    if final.exists():
        return shot["id"], "skipped"
    prompt = shot["prompt"]
    for attempt in (1, 2):
        try:
            tmp = d / f".{shot['id']}.tmp.mp4"
            t0 = time.time()
            cfg, meta = omni(client, prompt, str(tmp), shot["id"])
            os.replace(tmp, final)
            info = {"model": MODEL, "prompt": prompt, "config": cfg, "seconds_taken": round(time.time() - t0, 1),
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "attempts": attempt, **meta}
            (d / f"{shot['id']}.json").write_text(json.dumps(info, indent=1, default=str))
            return shot["id"], f"ok (attempt {attempt})"
        except Exception as e:
            print(f"[{shot['id']}] attempt {attempt} failed: {str(e)[:500]}", flush=True)
    return shot["id"], "FAILED"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    a = ap.parse_args()
    if not (ROOT / "shots.json").exists():
        raise SystemExit(f"no shot list: create {ROOT / 'shots.json'}, a list of {{\"id\", \"prompt\"}} "
                         "(README.md, \"B-roll\")")
    shots = [s for s in json.loads((ROOT / "shots.json").read_text()) if a.only in (None, s["id"])]
    client = genai.Client()  # reads GEMINI_API_KEY from the environment
    with ThreadPoolExecutor(max_workers=3) as ex:
        for sid, status in ex.map(lambda s: run(client, s), shots):
            print(f"{sid}: {status}", flush=True)


if __name__ == "__main__":
    main()
