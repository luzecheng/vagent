---
name: make-video
description: Turn a Chinese script into an animated story video — by default the robot style (a white-line robot walking one continuous night road past Codex-drawn props, with code-drawn chat bubbles, charts and coins), or on request the 「一笔」 line-art style; Chinese in portrait 1080×1920 for 视频号, English in landscape 1920×1080 for X — with the user's configured voice, music, subtitles and publish notes, using the local vagent tool; or, on request, the classic style (Chinese 视频号 + English X versions with infographic scenes). Use when the user runs /make-video, or asks to make / render / produce a video from a script (文稿做成视频、出片、做视频号视频).
---

# /make-video

Produce videos from one Chinese script with the local vagent tool. Everything stays on this computer:
never upload, post or publish anything, and never send the videos anywhere.

There are three styles:

| Style | When | Output |
|---|---|---|
| **Robot** (default) | always, unless the user asks otherwise | the white-line robot walks one continuous road through the user's favourite night in colour (navy sky, soft lit clouds, green hills; `robotfilm`, the default world since 2026-11-11), stops at Codex-drawn full-colour props and acts each shot out; Chinese portrait `robot2/robot2_portrait.mp4`, English landscape `robot2/robot2_en_landscape.mp4`, covers. See **2R** |
| **Story** | the user asks for 线条人 / 一笔 / 原来的故事版 | line-art story animation: Chinese in portrait 1080×1920 (`story_portrait.mp4`, for 视频号) and English in landscape 1920×1080 (`story_en_landscape.mp4`, for X), covers. This is the renderer's default, no flag needed. Both formats in both languages only when the user asks for it (横竖屏都要 / 也要横屏 / English portrait): add `--portrait` to the draft and render commands; one format only: `--only landscape` or `--only portrait` |
| **Classic** | the user asks for 原来的风格 / 信息图 / 经典版 | `zh_shipinhao.mp4`, `en_x_9x16.mp4`, covers, report |

## 0. Find vagent

This skill lives inside the vagent folder (`<vagent>/skill/make-video`, linked into `~/.claude/skills`).
Find `<vagent>` by resolving this skill's base directory:

```bash
cd "<this skill's base directory>" && cd "$(pwd -P)/../.." && pwd
```

If `<vagent>/.venv/bin/vagent` does not exist, vagent is not installed. Do not install anything on your
own: tell the user the three steps from the README (`git clone https://github.com/luzecheng/vagent`,
`cd vagent`, `./install.sh`) and wait.

## 1. Get the script

- If the user pasted the script, save it **verbatim** to `<vagent>/scripts/<short-name>.txt`
  (create the folder if needed). Pick `<short-name>` from the script's title or first line, in Chinese
  is fine (e.g. `小习惯.txt`); it becomes the output folder name. Do not edit the wording.
- If the user gave a file path, use that file as is.
- If there is no script, ask for it. Do not write one yourself.

## 2R. Robot style (default)

Read `<vagent>/robotfilm/robot_story.py` (top docstring) and the last episode's `robot2/beats.py` as the worked
example (`robotfilm/examples/讨论即开发_beats.py`, its props prompt next to it); shared helpers are in `robotfilm/fx.py`.
Do not stop for storyboard confirmation (the user wants the video made directly).

**Offline Robot mode (when Claude Code/Claude CLI is unavailable).** Robot production does not require an LLM at
render time: write the storyboard from the supplied script using the scene catalog, use the local configured TTS,
generate the props sheet with Codex, and run `story.render --stills` followed by `robotfilm.robot_story`. Skip the
Classic `vagent run` path's localization, LLM storyboard and LLM publish-copy calls. The Chinese Robot video can be
completed entirely offline; write `publish_notes.md` from the script manually, and make the English version only
when an English script is available. The renderer records `alignment*.json` with exact/Whisper alignment notes.

1. **Storyboard and voice.** Write `output/YYYY-MM-DD_<short-name>/storyboard.json` as in 2S step 1 (narration word
   for word, `narration_en`, `highlight`, 1–3 `quote`, cover fields), every shot `"scene": "walk"`. Then run
   `<vagent>/.venv/bin/python -m story.render <folder> --stills` in the background: it only synthesizes the voice
   and writes `timeline.json` / `timeline_en.json`, `build/voice*.wav`, `qa.md` (the slow part).
2. **Props.** Meanwhile have Codex draw one props sheet of nine objects for this episode (3 rows × 3, separate
   islands on black, full natural colour, no text) — copy `robotfilm/examples/彩色道具图提示词.txt` and change only
   the object list. Call `codex exec --skip-git-repo-check -s read-only - < prompt` (no reference image needed), copy the new image from
   `~/.codex/generated_images/` (diff the folder before/after) to `<folder>/robot2/frames/道具图_v1.png`. Look at it.
3. **Beats.** Write `<folder>/robot2/beats.py`: `PROPS` (the nine names in sheet order), `SOLID_PROPS = True` (colour
   props are cut out as solid objects), `MACHINE = None`, and
   `BEATS[shot id]` = walk seconds, pose, `stations` (props the robot stops at; `out` to remove them early),
   `fx` (code-drawn bubbles, charts, coins…). **No words in the picture while it plays**: the user wants only
   the subtitles (2026-11-12) — no sky labels, no gold quotes, no words in bubbles (the renderer hides labels and
   quotes unless beats set `SKY_WORDS` / `QUOTES = True`, which needs the user's request). The opening title card
   (cover title) stays. Tell each shot with props, actions, light and the camera instead.
   Make it alive — use these wherever the script allows (the user wants the best video code can make):
   - station options: `glow=True` or `(r,g,b)` for anything that gives light (fire, screen, lamp, open door),
     `flicker=True` for fire; `smoke=True` (or the height share it rises from) for fire, pots, coffee;
     `sway=True` for trees and plants; `taken=<s>` to make a prop vanish when the robot picks it up;
   - beat `hold=(prop, height, from_s)` puts a prop in the robot's hand (pair it with `taken` and a pose that
     bends down first, e.g. `lambda lt, d: BEND if lt < 0.8 else LIFT`); put the prop right in front of the
     robot (station x about 0.44);
   - the camera chooses shot sizes by itself (full when arriving, quotes close, talk shots take turns
     medium / full / close; the robot stands on the 38 % line); override with `cam="full"|"medium"|"close"`;
   - entering and leaving the frame: `enter=True` with a long `walk` (3.5–4 s, only on shots whose narration is
     long enough) makes the camera wait at the mark while the robot walks in from the left; `leave=<s>` makes
     it walk off to the right for the last s of the shot (pair a leave with an enter on the next shot: a cut);
   - camera angles (sparingly): `angle=` shows another view of the robot on a still shot (no walk, no
     enter/leave, no hold): `"low"` (looking up: resolve; tilts to more sky), `"over_shoulder"` (past the back
     of its head at what it faces), `"back"`, `"three_quarter"`, `"high"`. **At most two per film**, on the
     strongest lines — the user found more unnatural (2026-11-12); they dissolve in and out over 0.7 s;
   - still shots need something moving: `drift="leaves"` or `"paper"` blows a few across the frame; the colour
     night passes blurred grass in front of the lens on longer walks only (≥ ~0.2 frame widths, every other
     one): it comes in at the right edge and leaves at the left within the walk, never fades (automatic);
   - (only if an episode turns SKY_WORDS on) sky words via `fx.label` stay fixed on screen while the camera moves; draw anything that belongs to them
     (a strike-through, an arrow between two labels) inside `with fx.screen_space(cr):`, and measure labels
     with `fx.label_width`. Things standing in the world (bubbles over the robot, effects at a prop) are
     drawn normally and move with the camera.
   - keep the series identity stable: use the checked-in robot side/front/angle assets, declare exactly nine
     unique `PROPS` names in the same order as the generated props sheet, and set `SOLID_PROPS = True` for the
     colour-night series. The renderer validates this contract before spending time on a full render.
   - for a long shot, use a timed `actions` list instead of one static pose, for example
     `actions=[{"pose": "think", "duration": 2}, {"pose": "point", "duration": 3},
     {"pose": "look_up", "duration": 2}]`. Named poses include `stand`, `think`, `look_up`, `point`,
     `shrug`, `read`, `bow`, `hold`, `wave` and `work`; old pose dictionaries and callables remain supported.
     `shotlist` warns when a shot is longer than 14 seconds without a timed action sequence, so split it or add
     micro-actions before rendering.
   - set `SUBTITLE_PANEL = True` for new colour-night episodes. This adds a soft
     translucent subtitle panel while preserving keyword highlighting; old episodes without the flag keep their
     original subtitle pixels for reproducibility.
4. **Shot list, check sheets, then render.** `.venv/bin/python -m robotfilm.shotlist <folder>` writes
   `robot2/review/shotlist.md` (size, camera, what moves, cut or continuous, per shot) and prints warnings:
   fix every "nothing moves" and "three … in a row" in beats.py before rendering.
   `.venv/bin/python -m robotfilm.robot_story <folder> --sheet` (seconds) writes
   `robot2/review/sheet_*.png`: look at both, fix overlaps / props piling up / unreadable labels, repeat. After the
   voice is done: `.venv/bin/python -m robotfilm.robot_story <folder>` in the background (~3–4 min). Extract a few
   frames with ffmpeg and look at them. The colour night is the default; `--world robot` gives the original
   black-and-white world (then draw white line props with `robotfilm/examples/讨论即开发_道具图提示词.txt`, the last
   such sheet as reference, and no `SOLID_PROPS`), `--world story` the 「一笔」 forested world.
5. **Report** as in 2S steps 4–6 (qa items, files, publish notes), and say plainly that you only looked at
   frames: whether the motion looks natural is for the user to judge.

## 2S. Story style (on request: 线条人 / 一笔)

Read `<vagent>/story/README.md` first: it has the storyboard format, the writing rules and the scene list.

1. **Storyboard.** Create `<vagent>/output/YYYY-MM-DD_<short-name>/storyboard.json` (today's date). Turn the
   script into the protagonist's story: split the script, in order and word for word, into shots; give each
   shot one scene from the scene list with params, a `visual` line in Chinese, acts, 1–2 `quote` shots,
   `highlight` on most shots (1–2 key words of its narration, shown gold in the subtitles), and `corner` ①②③
   for numbered steps. Set `"script"` to the script file's path, and `"scenery": true` (forested mountains,
   street lamps, benches). The narration is the script
   itself: never add, drop or reword anything (the renderer checks this and stops on any difference).
   Also write the cover (`cover_title`, a short gold title; `cover_subtitle`, one line) and the English
   version: `narration_en` for every shot (faithful, natural English, not word-for-word), `quote_en` and
   `highlight_en` using words from that shot's `narration_en`, `title_en`, `cover_title_en`, `cover_subtitle_en`, and `*_en`
   versions of any Chinese text in scene params (e.g. `labels_en`).
2. **Draft and confirm.** Run `<vagent>/.venv/bin/python -m story.render <folder> --draft` (seconds; run it
   from `<vagent>`). Show the user, in Chinese, the cover title, a table of the shots (镜号 / 旁白 / English /
   画面 / 场景 / 金句) and the estimated length, and open `draft_portrait.png` (the Chinese draft). Wait for the user to confirm or change it; edit
   `storyboard.json` as they say and draft again. Do not start the full render before they confirm.
3. **Render.** Run `<vagent>/.venv/bin/python -m story.render <folder>` from `<vagent>` in the background.
   Tell the user how long: the voice is synthesized sentence by sentence and is the slow part (Chinese in the
   user's cloned CosyVoice voice, roughly 1–2 minutes per sentence the first time; English with Kokoro, a few
   minutes; sentences are cached, so reruns after visual changes take a few minutes).
4. **Check.** When it finishes, read `qa.md` and `qa_en.md` (sentences Whisper heard differently: 🟡 to
   listen to; Whisper also mishears, so a flag is not proof of a misreading) and look at the contact sheets
   (`contact_sheet_*.png`, `contact_sheet_en_*.png`) and covers (`cover_*.png`) yourself for anything broken
   (text overlapping, figures cut off).
5. **Publish notes.** Write `publish_notes.md` in the folder: for 视频号 in Chinese, 3 title options (≤ 20 字),
   a 2–3 sentence description, 3–5 hashtags; for X in English, a post under 280 characters with 1–2
   hashtags. All from the script's own content.
6. **Report** in Chinese and plain words: the videos (two by default: Chinese portrait and English landscape; four with `--portrait`) and their length, the qa items, anything you
   noticed on the contact sheets, and where the files are (videos, `cover_*.png` for uploading as the cover,
   `publish_notes.md`). Offer to open the videos (`open <file>`).

If a sentence is misread, fix it like the classic style does: cache-redo of that sentence, or a spoken-only
respelling in `config/zh_spoken.yaml` (`原文: 读法`), then rerun the render.

## 2C. Classic style (on request)

### Pick options from what the user said

| User says | Flag |
|---|---|
| 也要横屏 / 16:9 / landscape | `--landscape` |
| 加免责声明 / 不要免责声明 | `--disclaimer on` / `--disclaimer off` (default: automatic) |
| 超长也要完整做 / allow long | `--allow-long` |

Without a request, use no flags: the tool decides the disclaimer and pauses on over-long scripts.

### Run it

```bash
<vagent>/.venv/bin/vagent run <file> [flags]
```

Run it in the background and tell the user roughly how long it takes: a few minutes with the default
Kokoro voices, 10+ minutes if `config/local.yaml` selects the optional CosyVoice voice. When it finishes, the last console line names the output folder
(`<vagent>/output/YYYY-MM-DD_<short-name>/`).

### Report by exit code

**0: done.** Read `report.md` in the output folder and tell the user, in Chinese and in plain words:
- the items under「需要你重点看的地方」: 🔴 must be fixed before publishing, 🟡 worth a look;
- the durations of each video;
- where the files are: `zh_shipinhao.mp4`, `en_x_9x16.mp4`, `cover_zh.png`, `cover_en.png`,
  `publish_notes.md` (titles, description, X post), `report.md`.

Offer to open the two videos (`open <file>`), and the contact sheets `contact_sheet_*.png` for a quick
look. If `report.md` has trim suggestions, mention them as optional; apply none unless the user picks them.

**3: paused.** The tool needs a decision. Read `questions.md` in the output folder (or in `part*/`),
explain the options plainly, ask the user to choose, then rerun the same command with the chosen flag,
or with the script edited as the user decided. Finished stages are cached, so a rerun is quick up to the
point that changed.

**Any other code: failed.** Read the last lines of `run.log.jsonl` in the output folder (the final
entry has the error and a `retry` hint) and explain the cause. If `vagent doctor` would help
(missing dependency, model or font), run `<vagent>/.venv/bin/vagent doctor`.

## 3. Tidy the folder (all styles)

The user keeps only the two videos (Chinese + English) and `publish_notes.md` in each episode folder; no
covers, storyboard, voice, frames, logs or extra versions. The rest is still needed for quick fixes (a misread
sentence is re-voiced and re-rendered in minutes), so tidy only once the user is done with the episode:

- when the user says it is fine / final (没问题、定稿、可以了), tidy that episode's folder;
- at the start of a new /make-video, tidy every earlier episode folder that still holds extra files.

```bash
python3 "<this skill's base directory>/clean_output.py" <vagent>/output            # show what stays
python3 "<this skill's base directory>/clean_output.py" <vagent>/output --go       # videos to the top, generated files to the Trash; files it does not recognise stay and are listed
```

Report paths accordingly: after tidying, the videos sit at `<folder>/robot2_portrait.mp4` etc., not in `robot2/`.

## Rules

- Do not change the script's core points. In the story style the narration is the script word for word;
  in the classic style the tool may make light Chinese edits for smooth narration and lists every one in
  `report.md`; point them out.
- Numbers in the visuals come only from the script; never add data.
- Do not publish, upload, or fill in any platform form, even if asked in passing: give the user the
  files and the publish notes to post themselves.
- For many scripts at once in the classic style, suggest the inbox instead: drop `.txt` / `.md` files into
  `<vagent>/inbox/` and run `<vagent>/.venv/bin/vagent watch` (status in `inbox/STATUS.md`).
