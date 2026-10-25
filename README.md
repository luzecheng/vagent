# vagent

English · [中文](README.zh-CN.md)

One Chinese script in, two finished vertical videos out: a Chinese version for WeChat Channels (视频号) and an
English adaptation for X, with burned-in subtitles, covers, publish notes and an automatic QA report.
Everything runs on your own Mac. **vagent never uploads or publishes anything.**

## What you get

For each script, `output/YYYY-MM-DD_<name>/` contains:

| File | |
|---|---|
| `zh_shipinhao.mp4` | Chinese, 1080×1920, 30 fps, H.264 + AAC, subtitles burned in, laid out clear of WeChat Channels' buttons |
| `en_x_9x16.mp4` | English adaptation (not a literal translation), same format |
| `en_x_16x9.mp4` | optional landscape version (`--landscape`) |
| `zh.srt`, `en.srt` | subtitle files |
| `cover_zh.png` (3:4), `cover_en.png` (9:16) | covers; each video also opens on its cover and embeds it as artwork |
| `publish_notes.md` | WeChat Channels title (≤16 chars), description, topics; X post (≤280, counted the way X counts) |
| `report.md` | QA report: what needs your attention first (🔴 must fix / 🟡 worth a look), then every check |
| `contact_sheet_*.png` | one frame per scene, for a quick visual pass |
| `script_*_final.md`, `storyboard.json` | final scripts and the storyboard |

## Requirements

- macOS (the installer uses Homebrew; Apple silicon or Intel)
- Python 3.11+
- [Claude Code](https://claude.com/claude-code), logged in. The storyboard, the English adaptation and the publish
  notes are written through the local `claude` command line, so no API key is needed.
- About 3 GB of disk for the Kokoro voices and the Whisper model

## Install

```bash
git clone https://github.com/luzecheng/vagent.git
cd vagent
./install.sh              # ffmpeg, fonts, Python env, Kokoro voices, Whisper, and the /make-video skill
.venv/bin/vagent doctor   # checks everything is in place
```

Try it:

```bash
.venv/bin/vagent run tests/fixtures/small_habits.txt
```

If the `claude` command needs a proxy on your network, put it in `.env` (not committed):
`VAGENT_CLAUDE_PROXY=http://127.0.0.1:7890`.

## Use

Three entry points, one pipeline:

1. **In Claude Code:** `/make-video` followed by the script. Claude saves the script verbatim, runs vagent in the
   background and summarises `report.md` for you. If a decision is needed (e.g. the script is too long), it asks.
2. **Inbox folder:** run `vagent watch` and drop `.txt` / `.md` scripts into `inbox/`. Each script is processed in
   its own process: one that pauses or fails never blocks the others. Status is in `inbox/STATUS.md`.
3. **Command line:**

   ```bash
   vagent run script.txt                      # a file (or --text "...", or - for stdin)
   vagent run script.txt --landscape          # also render the 16:9 English version
   vagent run script.txt --disclaimer on|off  # force the disclaimer (default: automatic)
   vagent run script.txt --allow-long         # render past the 140 s cap instead of pausing
   vagent check output/<folder>               # rerun every check and rewrite report.md
   ```

A script can carry its own settings in a block at the top (handy for inbox files), and a line with only `---`
splits it into episodes:

```
---
allow_long: true
landscape: true
disclaimer: on
---
正文……
```

## How it works

- **Script.** Chinese gets at most light edits for smooth narration, each one listed in the report. English is
  freely adapted to the tone of X's investing / mindset community.
- **Voice.** Kokoro voices run locally, one sentence at a time, with per-character / per-word timings. Every
  sentence is then transcribed back with Whisper, and likely misreadings are flagged.
- **Storyboard.** Claude picks one of 15 scene components for each sentence. The result is validated:
  - a hook in the first 3 seconds;
  - every sentence covered once;
  - no component repeated three times in a row;
  - a data red line: only numbers stated in the script may appear.

  Anything invalid is sent back for a retry.
- **Render.** Frames are drawn with Pillow and composited with ffmpeg. Subtitles break at natural pauses and are
  balanced across lines. All text stays in the platform safe areas, and overflowing text is scaled down
  automatically.
- **Sound.** Voice and final mix sit at −16 LUFS. Background music is off by default (`audio.music` in
  `config/default.yaml`).
- **Disclaimer.** "Not financial advice" is added for investing / crypto / finance content, decided by keywords
  plus Claude's content classification.
- **Compliance scan.** It flags guaranteed-return claims, price predictions, buy/sell calls and FOMO wording. It
  never rewrites the text.

## Configuration

Later layers override earlier ones: `config/default.yaml` → `brand.yaml` → `config/local.yaml` (optional,
git-ignored, for settings specific to this machine) → command-line flags.

- `brand.yaml`: colours, fonts, watermark, disclaimer text, voices, target duration.
- **Optional Chinese voice:** `./install.sh --with-cosyvoice` (about 5 GB), then in `config/local.yaml`:

  ```yaml
  tts:
    zh: {provider: cosyvoice, model: cosyvoice-300m-sft, voice: "sft:中文男"}
  ```

  It runs on CPU only (Apple-silicon GPUs produce corrupted audio), at about 10 minutes per 2-minute narration.
- **Other TTS engines:** implement `vagent.tts.base.Provider` and register it in `vagent/tts/__init__.py`.

## Development

```bash
.venv/bin/python -m pytest -q tests
```

## License

[MIT](LICENSE). The voice models (Kokoro, CosyVoice), Whisper and the fonts (Inter, Noto Sans CJK) are downloaded
by the installer from their official sources under their own licenses; none of them is included in this repository.
