---
name: make-video
description: Turn a Chinese script into a Chinese 9:16 video for WeChat Channels (视频号) and an English 9:16 video for X, with subtitles, covers, publish notes and a QA report, using the local vagent tool. Use when the user runs /make-video, or asks to make / render / produce a short video from a script (文稿做成视频、出片、做视频号视频).
---

# /make-video

Produce videos from one Chinese script with the local vagent tool. Everything stays on this computer:
never upload, post or publish anything, and never send the videos anywhere.

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

## 2. Pick options from what the user said

| User says | Flag |
|---|---|
| 也要横屏 / 16:9 / landscape | `--landscape` |
| 加免责声明 / 不要免责声明 | `--disclaimer on` / `--disclaimer off` (default: automatic) |
| 超长也要完整做 / allow long | `--allow-long` |

Without a request, use no flags: the tool decides the disclaimer and pauses on over-long scripts.

## 3. Run it

```bash
<vagent>/.venv/bin/vagent run <file> [flags]
```

Run it in the background and tell the user roughly how long it takes: a few minutes with the default
Kokoro voices, 10+ minutes if `config/local.yaml` selects the optional CosyVoice voice. When it finishes, the last console line names the output folder
(`<vagent>/output/YYYY-MM-DD_<short-name>/`).

## 4. Report by exit code

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

- Do not change the script's core points. The tool may make light Chinese edits for smooth narration and
  lists every one in `report.md`; point them out.
- Numbers in the visuals come only from the script; never add data.
- Do not publish, upload, or fill in any platform form, even if asked in passing: give the user the
  files and the publish notes to post themselves.
- For many scripts at once, suggest the inbox instead: drop `.txt` / `.md` files into `<vagent>/inbox/`
  and run `<vagent>/.venv/bin/vagent watch` (status in `inbox/STATUS.md`).
