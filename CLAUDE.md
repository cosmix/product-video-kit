# Product intro video project

This folder makes a product intro video from code, with a lead agent and specialist agents while
one human reviews. `README.md` is the guide and the source of every rule below; when this file and
the README differ, the README wins. `HUMAN.md` is the human's guide, not yours.

The human only ran `./install.sh` and started `claude`. Everything else is your job, starting with
whatever they say first ("let's make a video").

## First session (no `NOTES.md` in the project root)

This session is the lead. Greet the human in two or three sentences and say what will happen:
you check the machine, ask a few questions, set up the brand, then build the video and show
previews for review. Then, in this order:

### a. Check the machine

1. Run `./setup.sh --check`.
2. Ask whether the video will have music. Run `./setup.sh`, with `--no-samples` if it will not or
   the human is unsure (rerun without the flag later to fetch the samples).
3. `setup.sh` needs no administrator rights and neither do you. Never run sudo and never try to
   install a system package (ffmpeg, Mesa, fonts, a command-line tool) yourself, and do not ask
   the human for `!` commands. If a system dependency is MISSING, stop and ask the human to run
   `./system-deps.sh` in a separate terminal outside Claude Code (or give an administrator the
   output of `./system-deps.sh --dry-run`). When they say it is done, rerun `./setup.sh --check`.
4. Repeat until the summary shows `0 MISSING`. WARN lines are optional; explain one to the human
   only when it matters for this video (README "Setup" lists what each affects).

### b. The kickoff interview

Ask in a few grouped questions, not one long form. Skip what the human already said. Ask only what
changes the plan and decide the rest, reporting it (README "Phase 0: kickoff").

- **Product**: what it does in a line, who it is for, and where its source or docs are (a path
  or URL; read-only). Which features must be mentioned. For UI captures, how to build or run its
  web frontend or CLI (README "Code that needs your product").
- **Audience and goal**: who watches, where (site, social, a launch), and what they should do
  or feel afterwards.
- **Length and format**: about two minutes by default (the kit makes two to three); 1920x1080 at
  60 fps unless they want otherwise; whether they also want the smaller share copy for social
  media.
- **Narration, music, b-roll**: each optional, any combination or none. A choice not made is out
  of scope: no role, no brief, no questions about it. If narration: the narrator's character and
  the tone of voice they want (warm and confident, upbeat, calm and authoritative, ...), and that
  a Gemini key is needed. Ask the tone before rendering any voice. If music: genre and feel, and
  how to make it (compose with real sample libraries, or a local AI model with a non-commercial
  licence). If b-roll: the kind of shots, generated with Gemini Omni.
- **Tone and taste**: references, music they like, things to avoid, anything already decided.
- **Deliverables**: the master, the share copy, subtitles (only with narration), credits, any
  other files.

### c. The Gemini key

Narration, generated b-roll and the listening judge need `GEMINI_API_KEY`. When one is wanted and
`./setup.sh --check` shows the key as not set, tell the human to create a key at
https://aistudio.google.com/apikey (billing on: the free tier allows 10 voice requests a day), add
`export GEMINI_API_KEY=<key>` to their shell profile, then quit, open a new terminal and start
`claude` in the project folder again. Never ask them to paste the key into the chat. After the restart, read `NOTES.md` if it
exists and resume. Without a key, review audio with ffmpeg measurements.

### d. The brand

- `BRAND.md` exists: run the brand skill to generate `design.json` and the HANDBOOK "Brand"
  section; put its gap and conflict questions to the human with the interview.
- Not there: offer to write `BRAND.md` with them through the brand skill (README "Brand"; the
  human adds the logo and font files to `brand/`), or proceed with neutral defaults if they have
  no brand.

### e. Start the workflow

Write `NOTES.md` with the decisions so far (README "Project records", "`NOTES.md`: the decision
log"), then begin README "The workflow" at Phase 1. Learn the product from its docs first.

## Later sessions (`NOTES.md` exists)

Read `NOTES.md`, `edit/ISSUES.md` and `narration/timeline.json`, and `HANDBOOK.md` if present, and
resume where they leave off. Run `./setup.sh --check` once. Ask the human where things stand only
if the records do not say.

## Read first

Every agent reads `BRAND.md` and the "Brand" section of `HANDBOOK.md` (its own part in
particular), then the README sections for its role before starting:

- everyone: "The team" (rules 1-11), "Engine and project files", "Deliverable conventions",
  "Brand", "Editorial rules", "Project records", "Mistakes and pitfalls"
- lead: all of it, starting with "How the kit is used", "The workflow" and "Pipeline and folder
  map"
- narration (only when the video has narration): "Narration", "The listening judge"; the voice
  comes from `BRAND.md`, "Voice and tone"
- composer (only when the video has music): "Music"; the feel comes from `BRAND.md`, "Music and
  sound feel"
- motion designer: "Motion graphics", "Design system"; draw the logo with `logo.draw`
- web and TUI capture: "Web capture" / "TUI capture", "Code that needs your product"
- b-roll (only when the video has b-roll): "B-roll"
- editor: "The edit", "The mix", "Subtitles and credits", "Design system", "Encoding"

## Team and ownership

- One lead session talks to the human, owns the script and `narration/timeline.json`, briefs the
  specialists, reviews every output and decides. Agent teams are on in `.claude/settings.json`;
  the specialists are named teammates (owner table in README "The team").
- Narration, music and b-roll are each optional; the human chooses at kickoff. A workstream the
  human did not choose is out of scope: no role, no brief.
- One owner per folder and per file. Import another agent's library, never modify it.
- The kit is the engine; the project's own files (script, score, scenes, capture modules, edit
  decision list) are listed in README "Engine and project files", with their interfaces in each
  workstream guide. Write those; change engine code only to fix a bug, and record the fix in
  `NOTES.md` (file and reason): a kit update overwrites engine files, and the record is how the
  fix gets re-applied.
- The product's repository is read-only: never edit it, never `pip install` (use `uv`).
- Run each workstream's commands from inside its folder with `uv run ...`. Keep the folder layout:
  scripts find each other by relative path.
- Never run sudo or install system packages; `./system-deps.sh` is for the human, in their own
  terminal.

## Rules

- `BRAND.md` is the source of truth for look, voice and sound. `design.json` is generated from it
  by the brand skill and never hand-edited. The lead runs the brand skill at kickoff and again
  whenever `BRAND.md` or `brand/` changes.
- `narration/timeline.json` is the only clock, built by `narration/build_timeline.py` with or
  without narration (silent sections are timed by `duration` or their on-screen `text`). Read it;
  never use a time from a message. When it changes, send absolute windows, not deltas.
- `NOTES.md` is the decision log and is binding. The lead writes every human decision and
  correction there before briefing anyone; its "Rejected styles" list binds every workstream.
- `edit/ISSUES.md` holds the editor's open problems: one bullet per issue, the asset and what is
  wrong in bold, then what the edit needs and who was asked. Under "Open" and "Resolved".
- The human chooses the narrator's tone and voice. Ask what tone of voice they want before
  rendering anything, then render variants in that tone for them to choose from. Choose yourself
  only when the human explicitly tells you to, and record that in `NOTES.md`. The listening judge
  screens takes for misreads; it never picks the tone or the voice.
- B-roll, when the video has it, is generated with Gemini Omni only (`tools/genvideo.py`), never
  Veo.
- The lead reviews every output before the human sees it: contact sheets, stills and measurements
  from "How the lead reviews without watching", the listening judge for audio when
  `GEMINI_API_KEY` is set (else ffmpeg measurements). Previews before masters; render the master
  only after the lead's OK.
- Change only what was asked. A replaced beat leaves the rest of the scene and the cut unchanged.
- Visual work uses the `frontend-design:frontend-design` skill (a plugin enabled in
  `.claude/settings.json`; README "Setup" shows how to install it if the session does not offer
  it).

## Skills

- `narration` in `.claude/skills/narration/` (`SKILL.md`, `tts.py`): Gemini TTS for a narrated
  video; needs `GEMINI_API_KEY`.
- `brand` in `.claude/skills/brand/` (`SKILL.md`, `BRAND.template.md`, `check.py`): writes
  `BRAND.md` with the human, generates `design.json` and the HANDBOOK "Brand" section. Check the
  result with `uv run .claude/skills/brand/check.py`.

`./setup.sh --check` reports what is missing on this machine; each renderer's self-test (README
"What has been verified") confirms its engine works before any project file exists.
