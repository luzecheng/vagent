# Story mode: line-art story videos

One Chinese script becomes a story-style animated video: 「一笔」, a figure drawn in glowing white lines with a
gold point of light in the chest, walks through night mountains, meets something on the way, and learns one
principle from it. Output is 1920×1080 landscape and 1080×1920 portrait, with the configured voice, soft music,
subtitles and 1–2 gold quote shots. Nothing is uploaded or published.

```
story/
  stage.py        the shared world (sky, stars, moon, mountains, ground) and the continuous camera
  hero.py         「一笔」: poses, pose blending, the lamp
  scenes/         one file per scene (see the list below); _props.py has the shared props
  narrate.py      TTS per sentence (vagent cache + voice), timing from the real audio, listening check
  render.py       reads storyboard.json and renders everything into the episode folder
```

## Making an episode

1. Make a folder, e.g. `output/2026-10-29_<name>/`, and write `storyboard.json` there (format below).
2. `.venv/bin/python -m story.render <folder> --draft` — contact sheets with estimated timing, no TTS
   (`draft_landscape.png`, `draft_portrait.png`): show these with the storyboard table and get it confirmed.
3. `.venv/bin/python -m story.render <folder>` — narration, listening check (`qa.md`), music, both videos
   (`story_landscape.mp4`, `story_portrait.mp4`), contact sheets, `timeline.json`. TTS is the slow part
   (cached per sentence, so a rerun after a visual change takes about two minutes).

## storyboard.json

```json
{
  "title": "先停一下",
  "principle": "遇到问题，先停下来想一想",
  "script": "scripts/<name>.txt",
  "cover_title": "先停一下", "cover_subtitle": "走得再急，也要看清脚下",
  "title_en": "Pause First", "cover_title_en": "Pause First", "cover_subtitle_en": "Look before the next step",
  "shots": [
    {"id": 1, "act": "第一幕", "narration": "路上总会有石头。走得太急，就会一次次被绊倒。",
     "narration_en": "There are always stones on the road. Rush, and you trip again and again.",
     "scene": "stumble", "params": {"mode": "trip", "times": 2}, "quote": "一次次被绊倒",
     "quote_en": "trip again and again", "visual": "夜路上，主角被一块石头绊倒，起身后又被同一块石头绊倒"}
  ]
}
```

- `narration`: the script's own words. Joined in order, the shots must equal the script exactly (whitespace
  aside); `render` checks this against `script` and stops on any difference. Split anywhere, even mid-sentence:
  a sentence is still spoken as one sentence and the cut lands where the voice reaches that word.
- `act`: shots in the same act follow each other with a sentence pause, a new act gets a longer pause.
- `quote` (optional, 1–2 per video): gold glowing words, fading in as the voice says them; use words that
  appear in that shot's narration, so they come in on time.
- `corner` (optional): "①" "②" "③" in the top corner, for numbered steps.
- `hold` (optional): seconds of silence after the shot; on the last shot the final subtitle stays on screen.
- `visual`: the picture in words, for the person reviewing the storyboard (not used by the renderer).
- Cover: `cover_title` (gold, short) and `cover_subtitle` (one line). The cover is the video's first frame
  (fading out before the first word), is embedded as the MP4's artwork, and is saved as `cover_*.png`.
- English version: `narration_en` on every shot (and `quote_en`, `title_en`, `cover_title_en`,
  `cover_subtitle_en`; `*_en` scene params such as `labels_en` replace the Chinese ones). Same shots and
  scenes, timed to the English voice (`config tts.en`). Files carry `_en`: `story_en_landscape.mp4`, `qa_en.md`…
  `--lang zh|en|all` picks the languages (all by default; English only when every shot has `narration_en`).

## Writing the story

- One principle per video; the hero meets something on the journey and learns from it. Story, not slides.
- Each shot: one action that shows its narration. Keep a prop running through the video (the stone, the lamp)
  so it reads as one journey.
- Pace: about 3–7 seconds per shot; a shot with a lot of narration (over ~10 s) may be split in two shots.
- The camera moves on its own between shots (looking up to the sky, back down, pulling back): order shots so
  sky shots sit together, to avoid the camera going up and down repeatedly.
- Don't copy the official 《原则》 animation (no pointed hat, no backpack traveler, none of its shots).
- Numbers and facts on screen only come from the script.

## Scenes

| scene | 名字 | what it shows | params |
|---|---|---|---|
| `walk` | 夜行 | walking through the mountains (opening, bridges) | `stop`, `gap` (a missing step in the road), `stone` (pass the stone), `path` (a gold road draws itself to the far mountains), `pull_back` |
| `look_up` | 抬头 | stops, looks up; the camera tilts into the stars | `lift`, `ease` |
| `stumble` | 绊倒 | the stone trips the hero | `mode`: `trip` (+`times`), `hurt` (rubbing the knee, fog hides the stone), `flower` (a glowing flower, reaching for it, trips again) |
| `wall` | 撞墙/断崖 | the road is blocked; the hero stops | `kind`: `wall` / `cliff` |
| `loop_path` | 绕圈脚印 | walking in a circle, footprints lap on lap | `laps`, `light_old` (old footprints light up into one ring) |
| `cloud` | 乌云 | blaming the outside: points at a dark cloud, it drifts off, the stone stays | |
| `constellation` | 星座连线 | stars join into shapes in the sky | `figures`: `crack`, `lamp`, `spiral`, `+`, `=`, `?`, or short text |
| `forecast` | 预测线 | a forecast line in the stars vs what really happened | `label` (e.g. a year), `stage`: `predict` / `split` |
| `spiral` | 螺旋上升 | a line climbs in turns, each higher | `turns`, `labels` |
| `cycle5` | 五步循环 | five lights in a ring light up and join | `labels` (default 目标 问题 诊断 设计 执行), `loops` |
| `gears` | 齿轮机器 | meshing gears turn (life as a machine) | `labels` |
| `fork` | 两条岔路 | the road splits: near-bright/far-dark vs near-dark/far-bright | `labels`, `choose` (0/1) |
| `mirror` | 镜子倒影 | the hero's reflection in still water | `differ` (the reflection shows what the hero doesn't see) |
| `council` | 多人对坐 | people in a ring, lights of different sizes over their heads | `weights`, `link` |
| `companions` | 同伴淡出 | companions fade out one by one | `count` |
| `pass_lamp` | 递灯 | an older figure hands the hero a lamp (the hero keeps it after) | |
| `reflect_light` | 反思之光 | reflection as light | `mode`: `chest` (chest light spreads), `lamp` (lamp lights the road), `stone` (sits by the stone, ring of light) |
| `question` | 问号 | one question mark breaks, a second lights up | |
| `writing` | 写字 | kneels and writes on a sheet | |
| `signpost` | 插路牌 | plants a glowing signpost by the stone (a rule) | |
| `face_camera` | 转身 | turns to face the viewer, lamp alight (closing question) | `zoom` |

A new scene is one file in `scenes/` with `TITLE`, `MIN_S`, `camera`, `hero`, `draw` (and optionally `speed`,
`front`); add its name to `scenes/__init__.py`.
