---
name: brand
description: Set up and apply the project's brand guidelines for the video. Writes or reads BRAND.md and the brand/ folder (logo, fonts, palette, reference assets), generates design.json (fonts, colours, grain, logo) from them, checks them with check.py, and records the brand rules in HANDBOOK.md. Use when the user mentions brand guidelines, BRAND.md, a logo, a palette, brand colours, fonts for the video, brand assets, or design.json.
---

# Brand

`BRAND.md` at the project root holds the brand guidelines; `brand/` holds the assets. Every
renderer reads `design.json` (README.md, "Design system" and "Brand"), which this skill generates
from them. Files next to this one: `BRAND.template.md` (the guidelines template) and `check.py`
(the checker).

## Rules

- `BRAND.md` is the source of truth. `design.json` is generated from it. After any edit to
  `BRAND.md` or `brand/`, run this skill again. Never hand-edit `design.json` unless `BRAND.md`
  says so.
- Never invent a brand value: a colour, font, logo rule, tone or legal line. When `BRAND.md` and
  `brand/` do not give it, ask the human.
- Never modify, rename, convert or delete files in `brand/`. Read them only. If an asset needs a
  new format (a PNG export of an SVG, a font from a web-only format), ask the human for it. The
  exceptions: `tools/fonts.py` writes `brand/fonts/resolved.json` and derived font files, and you
  may add a font with an open licence (see "Fonts by family").

## The brand/ layout

| Folder             | Holds                                                                                      |
| ------------------ | ------------------------------------------------------------------------------------------ |
| `brand/logo/`      | SVG preferred, else PNG at least 2000 px wide; a light-on-dark and a dark-on-light variant |
| `brand/fonts/`     | TTF, OTF or TTC files, with their licence files, in a folder per family                    |
| `brand/palette/`   | optional: exported palettes (`.json`, `.css`, `.ase`, `.txt`); read hex values from them   |
| `brand/reference/` | images or videos of the brand in use                                                       |

## When BRAND.md is missing

1. Interview the human with short questions, one topic at a time, in the order of the template's
   sections. Accept "none" or "skip". Do not suggest values for them to approve.
2. Write `BRAND.md` from `BRAND.template.md`, filled with their answers. Keep the guidance text
   only in sections they skipped.
3. Create `brand/logo/`, `brand/fonts/`, `brand/palette/` and `brand/reference/`.
4. Tell them exactly which files to drop in each folder (the table above, plus the font files and
   logo variants their answers named), and to run this skill again once they have.

## When BRAND.md exists

1. Read `BRAND.md` and list `brand/` recursively. Read the palette files for hex values; a value
   there that `BRAND.md` does not mention is a question, not a colour to use.
2. Write `design.json` at the project root. Keys (all optional; the loaders reject any other key):

   ```json
   {
     "fonts": {
       "family": "Inter",
       "regular": "brand/fonts/Body-Regular.ttf",
       "bold": "brand/fonts/Body-Bold.ttf",
       "italic": "brand/fonts/Body-Italic.ttf",
       "bold_italic": "brand/fonts/Body-BoldItalic.ttf",
       "weights": {
         "300": "brand/fonts/Body-Light.ttf",
         "800": "brand/fonts/Display-Black.ttf"
       },
       "mono": "brand/fonts/Mono-Regular.ttf"
     },
     "colors": {
       "background": "#0d0b12",
       "text": "#ece8f2",
       "secondary": "#9a93a8",
       "accent": "#7aa2ff"
     },
     "grain": 0.022,
     "logo": {
       "on_dark": "brand/logo/logo-white.svg",
       "on_light": "brand/logo/logo-black.svg"
     }
   }
   ```

   The values above show the shape only; take every value from `BRAND.md` and `brand/`.
   - Fonts: the body family fills `regular`, `bold`, `italic` and `bold_italic`. Renderers pick a
     font by weight, so a display face goes under `weights` at the weights titles use (or `bold`
     when titles are the only bold text); say which in the handbook. `mono` is the terminal and
     code font. A role is either a file path relative to the project root (ends in `.ttf`,
     `.otf` or `.ttc`) or a family name (`"Inter"`). `family` names the body family for every
     one of the four roles the file does not set itself; a family name under a role means that
     family at the role's weight (`"800": "Inter"` is Inter at 800). Name a family when the font
     is installed on the machine or its files are in `brand/fonts/`; the example above mixes
     both forms only to show them, so write the form `BRAND.md` and `brand/` support.
   - Colours: the four roles only, `#rrggbb`. Other brand colours stay in `BRAND.md` and the
     handbook; scenes use them by hex.
   - Grain: leave it out (default 0.022) unless the feel calls for film texture (raise it,
     0.03-0.05) or a flat, clean look (`0`).
   - Logo: `on_dark` is the variant for dark grounds (light ink), `on_light` for light grounds.
     Either may be absent. Motion draws it with `lib/logo.py`.

3. If `design.json` names a family, find its files from the project root and report what was
   found where (`brand/fonts`, `installed`) and every `WARN` (a weight or style the family lacks):

   ```bash
   uv run tools/fonts.py
   ```

   It searches `brand/fonts/` (recursively), then the fonts installed on the machine, and writes
   `brand/fonts/resolved.json`, which the loaders read. Installed fonts are used where they are,
   never copied into the project. See "Fonts by family" when a family is `MISSING`.

4. Run the checker from the project root and fix what it reports, by asking the human where the
   fix is theirs:

   ```bash
   uv run .claude/skills/brand/check.py
   ```

   `MISSING` lines must be resolved. A contrast `WARN` goes to the human as a question; do not
   change a brand colour to pass it.

5. Write a `## Brand` section into `HANDBOOK.md` (README.md, "`HANDBOOK.md`: the project's own
   handbook"; create the file if it does not exist, replace the section if it does). One short
   block per workstream the video has (narration, music and b-roll are optional; skip the block
   of one the human left out), each a list of rules quoted or condensed from `BRAND.md`:
   - narration: script voice and tone, words to use and avoid, the narration voice
   - music: genre, tempo, energy, what to avoid
   - motion: colours and their roles, fonts and weights, logo variant, clear space and minimum
     size, motion feel, things to avoid
   - captures (web and TUI): mono font, terminal colours, what the product UI keeps as is
   - edit: grounds, transitions, end card and credits, trademark and licence lines
6. Report every gap or conflict as a numbered question for the human: a section left blank, a
   file `BRAND.md` names that `brand/` lacks, a colour that differs between `BRAND.md` and a
   palette file, a font licence that may not allow video, a contrast warning, a missing logo
   variant.

## Fonts by family

When `BRAND.md` names a font that is neither installed nor in `brand/fonts/`:

- If it has an open licence that allows use in video (OFL, Apache), you may fetch it yourself.
  The GitHub repository `google/fonts` is a good source: `ofl/<name>/`, `apache/<name>/` or
  `ufl/<name>/`, where `<name>` is the family lowercased without spaces, and `METADATA.pb` there
  lists the font files. Save the font files and the licence file (`OFL.txt`, `LICENSE.txt`) into
  `brand/fonts/<Family>/`, then run `uv run tools/fonts.py` again.
- For any other font, ask the human to install it on this machine or to put its files and
  licence in `brand/fonts/<Family>/`. Never fetch a commercial font.

## Checking a project later

`uv run .claude/skills/brand/check.py [project-root]` prints one line per item (`ok`, `WARN`,
`MISSING`) and exits 1 on any `MISSING`. `WARN design.json ... rerun the brand skill` means
`BRAND.md` or a file in `brand/` changed after `design.json` was written: run this skill again.
For family-named fonts it also runs `tools/fonts.py --check` and reports each family it cannot
find (`MISSING`) and each style it cannot match exactly (`WARN`).
