# /// script
# requires-python = ">=3.11"
# dependencies = ["google-genai>=2.25.0"]
# ///
"""Ask a Gemini model to listen to (or watch) media files and answer a question.

Usage: uv run tools/listen.py "question" file1 [file2 ...] [--model NAME]
Logs the call's token counts to usage.jsonl (tools/usage_log.py) and prints them to stderr.
"""
import argparse
import sys
import time

from google import genai

import usage_log

p = argparse.ArgumentParser()
p.add_argument("question")
p.add_argument("files", nargs="+")
p.add_argument("--model", default="gemini-3.8-flash")
a = p.parse_args()

client = genai.Client()
parts = []
for f in a.files:
    up = client.files.upload(file=f)
    while up.state and up.state.name == "PROCESSING":
        time.sleep(2)
        up = client.files.get(name=up.name)
    parts.append(f"File: {f}")
    parts.append(up)
parts.append(a.question)
resp = client.models.generate_content(model=a.model, contents=parts)
usage = usage_log.from_generate(resp.usage_metadata)
usage_log.log("listen", a.model, usage, files=a.files)
print(usage_log.summary(usage), file=sys.stderr)
print(resp.text)
