"""The one core pipeline every entry point (CLI, inbox watcher, /make-video skill) calls."""
from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import re

from .audio import narration as narr
from .log import RunLog
from .script import parse
from .subtitles import segment


class Paused(Exception):
    """The task needs a human decision; questions.md explains which."""


def slug_for(text: str, origin: str) -> str:
    base = re.sub(r"[^\w-]+", "-", origin).strip("-_").lower()  # \w keeps Chinese file names readable
    if base and base not in ("text", "stdin"):
        return base[:40]
    return "script-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:6]


HOW_TO_ANSWER = [
    "", "## 怎么回复", "",
    "- 命令行运行的：按上面的选项改稿或加参数，重新运行同一条命令（已完成的部分会直接复用）。",
    "- 放进 inbox 的：稿件已移到 `inbox/paused/`。改好后放回 `inbox/` 即可；要用参数时，在稿件最开头加三行：",
    "", "  ```", "  ---", "  allow_long: true", "  ---", "  ```"]


def write_questions(out: Path, title: str, body: list[str]) -> None:
    (out / "questions.md").write_text("\n".join([f"# 需要你决定：{title}", "", *body, *HOW_TO_ANSWER, ""]),
                                      encoding="utf-8")


def _script_md(script: parse.Script, lang: str, changes: list[dict] | None = None) -> str:
    rows = [f"# {'中文终稿' if lang == 'zh' else 'English final script'}", ""]
    rows += [s.text for s in script.sentences]
    if changes:
        rows += ["", "## 口播微调（与原稿的差异）", ""]
        rows += [f"- 第 {c['id']} 句：“{c['before']}” → “{c['after']}”" + (f"（{c['reason']}）" if c["reason"] else "")
                 for c in changes]
    return "\n".join(rows) + "\n"


def run_script(text: str, origin: str, config: dict, stage: str = "all", out_dir: Path | None = None) -> int:
    """0 done, 3 paused (questions.md written). A script split by `---` lines yields part1/, part2/, ..."""
    from .script.frontmatter import episodes

    out = out_dir or Path(config["paths"]["output"]) / f"{date.today().isoformat()}_{slug_for(text, origin)}"
    parts = episodes(text)
    if len(parts) > 1:
        codes = [_run_one(part, config, out / f"part{i}", stage) for i, part in enumerate(parts, 1)]
        return 3 if 3 in codes else 0
    return _run_one(text, config, out, stage)


def _run_one(text: str, config: dict, out: Path, stage: str) -> int:
    out.mkdir(parents=True, exist_ok=True)
    (out / "questions.md").unlink(missing_ok=True)  # a question from an earlier run is answered by rerunning
    log = RunLog(out / "run.log.jsonl")
    try:
        return _run(text, config, out, log, stage)
    except Paused as exc:
        log.event("pause", str(exc))
        print(f"\nPaused: see {out / 'questions.md'}")
        return 3
    except Exception as exc:
        log.error("pipeline", f"{type(exc).__name__}: {exc}",
                  retry=f"fix the cause, then rerun the same command (finished stages are cached): output {out}")
        raise


def _run(text: str, config: dict, out: Path, log: RunLog, stage: str) -> int:
    script = parse.split(text)
    if not script.sentences:
        raise ValueError("the script is empty after cleaning")
    estimate = parse.estimate_seconds(script, "zh", config)
    limits = config["duration"]
    log.event("parse", f"{len(script.sentences)} sentences, estimated zh {estimate:.0f}s")
    if estimate > limits["hard_cap_s"] * limits["max_speedup"] + 5 and not limits.get("allow_long"):
        write_questions(out, "稿件偏长", [
            f"按当前音色估算，中文口播约 {estimate:.0f} 秒，超过 {limits['hard_cap_s']} 秒上限"
            f"（X 非会员视频上限 2:20），即使加速到 {limits['max_speedup']} 倍也放不下。",
            "", "请选择一项后重新运行：",
            "1. 分成几集：在稿件里分集的地方单独写一行 `---`，每集各出一套成片（part1/、part2/ …）；",
            f"2. 精简到约 {int(limits['hard_cap_s'] * config['tts']['rate']['zh_chars_per_s'] * 0.9)} 字以内；",
            "3. 仍然完整制作：加 `--allow-long`（英文版超过 2:20 时 X 非会员无法上传）。"])
        raise Paused(f"estimated {estimate:.0f}s exceeds the hard cap")

    from .script.localize import localize

    zh_script, en_script, changes = localize(script, config, log)
    (out / "script_zh_final.md").write_text(_script_md(zh_script, "zh", changes), encoding="utf-8")
    (out / "script_en_final.md").write_text(_script_md(en_script, "en"), encoding="utf-8")
    (out / "build").mkdir(exist_ok=True)
    (out / "build" / "zh_changes.json").write_text(json.dumps(changes, ensure_ascii=False, indent=1), encoding="utf-8")

    results = {}
    for lang, lang_script in (("zh", zh_script), ("en", en_script)):
        narration = narr.narrate(lang_script, lang, config, log)
        if narration.status == "OVER_LIMIT":
            write_questions(out, "成片超过时长上限", [
                f"{lang} 配音实际时长 {narration.duration:.1f} 秒，加速到 {limits['max_speedup']} 倍仍超过 "
                f"{limits['hard_cap_s']} 秒。", "", "请选择：分成两集 / 精简字数 / 加 `--allow-long` 完整制作。"])
            raise Paused(f"{lang} narration {narration.duration:.1f}s exceeds the hard cap")
        narr.save(narration, out / "build", lang)
        screens = segment.build(narration.timeline, lang, config)
        (out / f"{lang}.srt").write_text(segment.srt(screens), encoding="utf-8")
        narration.timeline["screens"] = [s.__dict__ for s in screens]
        (out / "build" / f"timeline_{lang}.json").write_text(
            json.dumps(narration.timeline, ensure_ascii=False, indent=1), encoding="utf-8")
        results[lang] = narration
        log.event("subtitle", f"{lang}: {len(screens)} screens, status {narration.status}")
    from .qa import audio_check

    report = ["# 配音回听（Whisper）", ""]
    from . import cache as cachemod
    from .qa.asr import ASR_MODEL

    asr_store = cachemod.Cache(config["paths"]["cache"], "asr")
    asr_results = {}
    for lang, n in results.items():
        digest = cachemod.key(ASR_MODEL, lang, hashlib.sha256(n.audio.tobytes()).hexdigest(),
                              [(x["id"], x["text"]) for x in n.timeline["sentences"]])
        result = asr_store.get_json(digest)
        if result is None:
            result = audio_check.check(n.audio, n.timeline, lang)
            asr_store.put_json(digest, result)
        asr_results[lang] = result
        report.append(audio_check.markdown(result))
        log.event("asr", f"{lang}: error rate {result['overall_error_rate']:.1%}, {len(result['flagged'])} flagged")
    (out / "build" / "asr_check.md").write_text("\n".join(report), encoding="utf-8")
    (out / "build" / "asr_check.json").write_text(json.dumps(asr_results, ensure_ascii=False, indent=1), encoding="utf-8")
    if stage == "audio":
        for lang, n in results.items():
            print(f"{lang}: {n.duration:.1f}s ({n.timeline['status']}), speed {n.speed}")
        print(f"audio stage done: {out}")
        return 0

    # ---------------------------------------------------------------- storyboard
    from .plan import planner
    from .plan.timing import scene_specs
    from .script.classify import decide_disclaimer

    zh_lines = {s["id"]: s["text"] for s in results["zh"].timeline["sentences"]}
    en_lines = {s["id"]: s["text"] for s in results["en"].timeline["sentences"]}
    timings = {s["id"]: (s["start"], s["end"]) for s in results["zh"].timeline["sentences"]}
    board = planner.plan(zh_lines, en_lines, timings, config, log)
    disclaimer = decide_disclaimer(script.text, board.content_type, board.disclaimer.reason,
                                   config.get("disclaimer_override"))
    intro = config["video"].get("cover_intro_s", 0.0)
    specs = {lang: scene_specs(board, results[lang].timeline, lang, intro) for lang in ("zh", "en")}
    storyboard = {**board.model_dump(), "disclaimer_decision": disclaimer,
                  "timing": {lang: [{"id": s.id, "start": s.start, "end": s.end, "reveals": s.reveals}
                                    for s in specs[lang]] for lang in specs}}
    (out / "storyboard.json").write_text(json.dumps(storyboard, ensure_ascii=False, indent=1), encoding="utf-8")
    log.event("plan", f"{len(board.scenes)} scenes, type {board.content_type}, disclaimer "
                      f"{'on' if disclaimer['on'] else 'off'}")
    if stage == "plan":
        print(f"storyboard written: {out / 'storyboard.json'}")
        return 0

    # ---------------------------------------------------------------- render
    from .audio.mix import mix
    from .publish import notes as publish
    from .render import engine
    from .render.cover import render_cover
    from .render.theme import theme as make_theme, variant as make_variant

    fps = config["video"]["fps"]
    brand = config.get("brand", {})
    account = (brand.get("account") or {}).get("watermark", "")
    seed = int(hashlib.sha256(script.text.encode("utf-8")).hexdigest()[:8], 16)
    outro = 2.8 if disclaimer["on"] else 1.0
    stats: dict = {"disclaimer": disclaimer, "outputs": {}}

    # ---------------------------------------------------------------- covers + publish notes
    zh_text = "".join(s["text"] for s in results["zh"].timeline["sentences"])
    en_text = " ".join(s["text"] for s in results["en"].timeline["sentences"])
    notes, notes_md = publish.draft(zh_text, en_text, disclaimer, brand, config, log)
    (out / "publish_notes.md").write_text(notes_md, encoding="utf-8")
    covers = {}  # made first: the videos open on them
    for lang, title, sub, size, name in (("zh", notes.cover_title_zh, notes.cover_sub_zh, (1080, 1440), "cover_zh.png"),
                                          ("en", notes.cover_title_en, notes.cover_sub_en, (1080, 1920), "cover_en.png")):
        records = render_cover(title, sub, make_theme(config, lang), size, out / name, account)
        covers[name] = [{"text": r.text, "box": r.box.__dict__, "font": r.font, "size": r.size} for r in records]
    log.event("publish", "covers and publish_notes.md written (nothing is posted)")
    stats["covers"] = covers
    cover_text = {"zh": (notes.cover_title_zh, notes.cover_sub_zh), "en": (notes.cover_title_en, notes.cover_sub_en)}

    outputs = [("zh", "zh_shipinhao", "zh_shipinhao.mp4", (1080, 1920)),
               ("en", "en_x", "en_x_9x16.mp4", (1080, 1920))]
    if config["video"].get("landscape_16x9"):
        outputs.append(("en", "en_x_16x9", "en_x_16x9.mp4", (1920, 1080)))
    audio_cache: dict[str, tuple] = {}
    for lang, vname, filename, (width, height) in outputs:
        theme = make_theme(config, lang)
        variant = make_variant(vname, width, height)
        total = results[lang].duration + outro
        scenes = list(specs[lang])
        end_params = {"disclaimer": brand.get("disclaimer", {}).get(lang, "") if disclaimer["on"] else "",
                      "account": account}
        scenes.append(engine.SceneSpec("end", "end_card", end_params, results[lang].duration, total))
        if lang not in audio_cache:
            audio_cache[lang] = mix(out / "build" / f"{lang}.wav", total, seed, out / "build" / f"mix_{lang}",
                                    music=config.get("audio", {}).get("music", True))
        final_audio, audio_stats = audio_cache[lang]
        clips = engine.render_scenes(scenes, theme, variant, fps, config["paths"]["cache"], log)
        scene_stats = [{"id": c["id"], "records": c["records"], "scale": s.scale} for c, s in zip(clips, scenes)]
        if intro:
            frame = out / "build" / f"cover_frame_{vname}.png"
            records = render_cover(*cover_text[lang], theme, (width, height), frame, account, area=variant.content)
            clip = engine.still_clip(frame, intro, fps, out / "build" / f"cover_frame_{vname}.mp4")
            clips = [{"id": "cover", "path": str(clip)}] + clips
            scene_stats.insert(0, {"id": "cover", "scale": 1.0, "records": [
                (r.text, r.box.__dict__, r.font, r.size) for r in records]})
        subs = engine.subtitle_images(results[lang].timeline["screens"], theme, variant,
                                      out / "build" / f"subs_{vname}")
        watermark = engine.watermark_image(theme.watermark, theme, variant, out / "build" / f"wm_{vname}")
        engine.composite(clips, subs, final_audio, out / filename, variant, fps, out / "build" / f"compose_{vname}",
                         watermark, duration=total)
        engine.embed_artwork(out / filename, out / ("cover_zh.png" if lang == "zh" else "cover_en.png"))
        stats["outputs"][filename] = {"duration": round(total, 2), "audio": audio_stats, "variant": vname,
                                      "scenes": scene_stats,
                                      "subtitles": [{"lines": sb.lines, "box": sb.box.__dict__, "size": sb.size}
                                                    for sb in subs]}
        log.event("render", f"{filename} written ({total:.1f}s, {audio_stats['final_lufs']:.1f} LUFS)")

    (out / "build" / "render_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1, default=str),
                                                     encoding="utf-8")

    # ---------------------------------------------------------------- checks + report
    from .qa import report as qa_report

    data = qa_report.write(out, config, notes.cover_title_zh.replace("/", ""), log)
    marks = qa_report.attention(data)
    errors = sum(1 for level, _ in marks if level == "error")
    log.event("report", f"report.md written: {errors} must-fix, {len(marks) - errors} to review")
    print(f"done: {out}")
    return 0
