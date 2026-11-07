---
name: make-video
description: Turn a Chinese script into a story-style line-art animated video (「一笔」 walking through night mountains; Chinese in portrait 1080×1920 for 视频号, English in landscape 1920×1080 for X) with the user's configured voice, music, subtitles and publish notes, using the local vagent tool; or, on request, the classic style (Chinese 视频号 + English X versions with infographic scenes). Use when the user runs /make-video, or asks to make / render / produce a video from a script (文稿做成视频、出片、做视频号视频).
---

# /make-video

Produce videos from one Chinese script with the local vagent tool. Everything stays on this computer:
never upload, post or publish anything, and never send the videos anywhere.

There are two styles:

| Style | When | Output |
|---|---|---|
| **Story** (default) | always, unless the user asks otherwise | line-art story animation: Chinese in portrait 1080×1920 (`story_portrait.mp4`, for 视频号) and English in landscape 1920×1080 (`story_en_landscape.mp4`, for X), covers. This is the renderer's default, no flag needed. Both formats in both languages only when the user asks for it (横竖屏都要 / 也要横屏 / English portrait): add `--portrait` to the draft and render commands; one format only: `--only landscape` or `--only portrait` |
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

## 2S. Story style (default)

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

## Rules

- Do not change the script's core points. In the story style the narration is the script word for word;
  in the classic style the tool may make light Chinese edits for smooth narration and lists every one in
  `report.md`; point them out.
- Numbers in the visuals come only from the script; never add data.
- Do not publish, upload, or fill in any platform form, even if asked in passing: give the user the
  files and the publish notes to post themselves.
- For many scripts at once in the classic style, suggest the inbox instead: drop `.txt` / `.md` files into
  `<vagent>/inbox/` and run `<vagent>/.venv/bin/vagent watch` (status in `inbox/STATUS.md`).
