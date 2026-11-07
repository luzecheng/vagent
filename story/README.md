# Story mode: line-art story videos

One Chinese script becomes a story-style animated video: 「一笔」, a figure drawn in glowing white lines with a
gold point of light in the chest, walks through night mountains, meets something on the way, and learns one
principle from it. Output: Chinese in 1080×1920 portrait (视频号), English in 1920×1080 landscape (X); `--portrait`
renders both formats for each language, `--only landscape|portrait` just one. With the configured voice, soft music,
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
   (`draft_portrait.png` for Chinese, `draft_en_landscape.png` for English; with `--portrait` both formats of each): show these
   with the storyboard table and get it confirmed.
3. `.venv/bin/python -m story.render <folder>` — narration, listening check (`qa.md`), music, both videos
   (`story_portrait.mp4` and `story_en_landscape.mp4`; all four with `--portrait`), contact sheets, `timeline.json`. TTS is the slow part
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
  Lines that are only a 【heading】 or a Markdown `# heading` are not spoken, and `**bold**` marks are left out.
  A narration ending in a line break (`"阻碍财富积累的几个习惯\n"`, a title line with no full stop) ends its sentence there.
- `act`: shots in the same act follow each other with a sentence pause, a new act gets a longer pause.
- `quote` (optional, 1–2 per video): gold glowing words, fading in as the voice says them; use words that
  appear in that shot's narration, so they come in on time.
- `highlight` (optional): 1–2 key words of that shot's narration, shown in gold in the subtitles (on a phone
  the eye catches them first); `highlight_en` picks words from `narration_en`. A keyword never breaks across
  subtitle rows; English keywords match whole words, any case.
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
- Pace: about 3–7 seconds per shot. A line shorter than its scene's action (e.g. "可你得问问自己：" on `mirror`) makes the
  voice wait in silence for the picture; `render` lists every such wait over 0.6 s: merge that line with a
  neighbouring shot. A shot with a lot of narration (over ~10 s) may be split in two shots.
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
| `strike` | 划掉旧观点 | an old belief in the sky is struck out in red and sinks; the new view rises in gold | `old`, `new` (+ `old_en`, `new_en`) |
| `ring_meet` | 圆环相遇 | two lights leave one point on a ring in opposite directions and meet at the top | `labels` (+`labels_en`), `meet` (+`meet_en`), `until` (0.5: only out to the sides) |
| `compare` | 对比卡 | the hero and someone else face each other across one shared thing; a thought bubble over each head shows how each sees it (no `quote` on this shot) | `topic`, `left`, `right` (string or list of lines; + `_en`), `poses` ([hero, other], e.g. ["bend", "lamp_up"]) |
| `face_camera` | 转身 | turns to face the viewer, lamp alight (closing question) | `zoom` |
| `book` | 书 | an open book floats in the sky, lines of text write themselves in (reading, studying) | `flips` (pages riffle past: reading fast), `close` (folds shut at the end), `title` (+`title_en`) |
| `screen` | 屏幕 | a phone or laptop screen lights up and fills with content (AI answers, scrolling) | `device`: `phone` / `laptop`, `lines` (up to 4 short words, + `lines_en`), `off` (the screen switches off at the end: "关掉屏幕") |
| `chat` | 对话框 | a conversation with AI: your bubbles (white, left) and AI's (gold, right) appear in turn, AI typing first | `bubbles` (short words from the script, yours first, + `bubbles_en`), `count` (bubbles without words) |
| `map` | 导航 | a map; a gold route draws itself and a light follows it (following directions) | `off` (navigation switches off halfway: the route fades and the light stops at a junction) |
| `chart` | 曲线图 | axes and a curve drawing itself (growth, decline, ups and downs) | `trend`: `up` / `down` / `wave` / `up_down` / `down_up`, `values` (numbers from the script only), `labels` ([left, right], + `labels_en`), `color`: `gold` / `red` / `white` |

The object scenes (`book` … `chart`) float the object beside the hero, clear of the moon (in portrait, wide
objects go overhead); use them when the narration names the thing, so the picture shows what is said.

A new scene is one file in `scenes/` with `TITLE`, `MIN_S`, `camera`, `hero`, `draw` (and optionally `speed`,
`front`); add its name to `scenes/__init__.py`.
