"""Phase-2 demos: component gallery reel and safe-area overlay image."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import ImageDraw

from . import engine
from .components import REGISTRY
from .gallery import SAMPLES
from .theme import theme as make_theme, variant as make_variant

NAMES_ZH = {"hook": "大字钩子", "keyword": "关键词", "compare_cards": "对比卡片", "trend": "趋势曲线",
            "short_vs_long": "短期 vs 长期", "timeline": "时间线", "bars": "柱状对比", "big_number": "大数字",
            "quote": "引用语", "checklist": "清单", "strike": "划掉旧观点", "three_things": "三件事",
            "question_stack": "连续提问", "choice_consequence": "选择 vs 后果", "punchline": "金句放大"}


def gallery_reel(lang: str, out: Path, config: dict, log, seconds: float = 3.4) -> Path:
    vname = "zh_shipinhao" if lang == "zh" else "en_x"
    theme, variant = make_theme(config, lang), make_variant(vname)
    fps = config["video"]["fps"]
    scenes, screens, t = [], [], 0.0
    for name in REGISTRY:
        reveals = [t + 0.3 + i * 0.6 for i in range(5)]
        scenes.append(engine.SceneSpec(name, name, SAMPLES[lang][name], t, t + seconds, reveals))
        label = NAMES_ZH[name] if lang == "zh" else name.replace("_", " ")
        screens.append({"lines": [label], "start": t + 0.2, "end": t + seconds - 0.2})
        t += seconds
    work = out.parent / f"build_{lang}"
    clips = engine.render_scenes(scenes, theme, variant, fps, config["paths"]["cache"], log)
    subs = engine.subtitle_images(screens, theme, variant, work / "subs")
    silence = work / "silence.wav"
    sf.write(silence, np.zeros(int(t * 48000), np.float32), 48000)
    engine.composite(clips, subs, silence, out, variant, fps, work, duration=t)
    return out


def safe_area_overlay(lang: str, out: Path, config: dict) -> Path:
    vname = "zh_shipinhao" if lang == "zh" else "en_x"
    theme, variant = make_theme(config, lang), make_variant(vname)
    scene = engine.SceneSpec("demo", "three_things", SAMPLES[lang]["three_things"], 0, 4, [0.2, 0.8, 1.4])
    image, records = engine.render_frame(scene, 3.0, theme, variant)
    d = ImageDraw.Draw(image)
    for box, color, label in ((variant.safe, (255, 255, 255), "safe"), (variant.content, (60, 200, 192), "content"),
                              (variant.subtitles, (232, 181, 71), "subtitles")):
        d.rectangle([box.x, box.y, box.right, box.bottom], outline=color, width=4)
        d.text((box.x + 8, box.y + 8), label, fill=color)
    for record in records:
        b = record.box
        d.rectangle([b.x, b.y, b.right, b.bottom], outline=(255, 96, 88), width=2)
    image.save(out)
    return out


def narrated_demo(run_dir: Path, out: Path, config: dict, log, last_sentence: int = 9) -> Path:
    """First sentences of a phase-1 run, with a hand-written storyboard, to show audio/subtitle/scene sync."""
    import json

    timeline = json.loads((run_dir / "build/timeline_zh.json").read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in timeline["sentences"]}
    start = lambda i: by_id[i]["start"]  # noqa: E731
    end_t = by_id[last_sentence]["clip_end"] + 0.4
    plan = [
        ("hook", {"text": "目标没完成，往往不是你不够努力", "sub": "每年立的目标，到年底还剩几个？"}, 0.0, start(3) - 0.3,
         [start(2)]),
        ("keyword", {"word": "把习惯做小", "caption": "小到今天状态再差，也能做到"}, start(3) - 0.3, start(6) - 0.3, []),
        ("checklist", {"title": "从小事开始", "items": ["每天读一页", "每天走十分钟", "每天写三句话"]}, start(6) - 0.3,
         end_t, [start(6), start(7), start(8)]),
    ]
    scenes = [engine.SceneSpec(f"s{i}", name, params, a, b, reveals)
              for i, (name, params, a, b, reveals) in enumerate(plan)]
    theme, variant = make_theme(config, "zh"), make_variant("zh_shipinhao")
    screens = [s for s in timeline["screens"] if s["start"] < end_t]
    clips = engine.render_scenes(scenes, theme, variant, config["video"]["fps"], config["paths"]["cache"], log)
    subs = engine.subtitle_images(screens, theme, variant, out.parent / "build_narrated/subs")
    engine.composite(clips, subs, run_dir / "build/zh.wav", out, variant, config["video"]["fps"],
                     out.parent / "build_narrated", duration=end_t)
    return out
