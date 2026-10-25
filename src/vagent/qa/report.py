"""Assemble report.md: run every check on the finished outputs and put what needs a human on top."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from pydantic import BaseModel, Field

from . import checks, compliance
from .checks import Check
from .layout import missing_glyphs

ICON = {"ok": "✅", "warn": "🟡", "error": "🔴"}
PLATFORM = {"zh_shipinhao.mp4": ("中文 · 视频号", "shipinhao"), "en_x_9x16.mp4": ("英文 · X 竖屏", "x"),
            "en_x_16x9.mp4": ("英文 · X 横屏", "x")}


# ---------------------------------------------------------------- trim suggestions (only when long)
class Cut(BaseModel):
    sentence_ids: list[int] = Field(min_length=1, description="consecutive sentence ids to drop or shorten")
    action: str = Field(description="删除 or 缩短")
    suggestion: str = Field("", description="for 缩短: the shorter Chinese wording; empty for 删除")
    reason: str = Field(description="one short Chinese sentence: why this can go without losing the core point")


class Trim(BaseModel):
    cuts: list[Cut]


TRIM_SYSTEM = """你是短视频剪辑编辑。稿件偏长，需要给作者精简建议（只是建议，作者自己决定）。
原则：保留核心观点、开头钩子和结尾金句；优先删除重复论证、铺垫过长、与主线弱相关的句子；
可以把长句改短。不要改变作者的观点和语气。用中文回答，只输出 JSON。"""


def trim_suggestions(timeline: dict, target_s: float, config: dict, log=None) -> list[dict]:
    from .. import cache as cachemod
    from ..llm.client import structured

    sentences = timeline["sentences"]
    seconds = {s["id"]: s["end"] - s["start"] for s in sentences}
    excess = timeline["duration"] - target_s
    user = (f"当前时长 {timeline['duration']:.0f} 秒，目标 {target_s:.0f} 秒以内，约需减少 {excess:.0f} 秒。\n"
            "每句前是编号和朗读秒数：\n" + "\n".join(f"{s['id']}. ({seconds[s['id']]:.1f}s) {s['text']}"
                                               for s in sentences))

    def check(trim: Trim):
        out = []
        for cut in trim.cuts:
            if any(i not in seconds for i in cut.sentence_ids):
                out.append(f"unknown sentence id in {cut.sentence_ids}")
            if cut.sentence_ids[0] == sentences[0]["id"] and cut.action == "删除":
                out.append("do not delete the opening hook sentence")
        return out

    store = cachemod.Cache(config["paths"]["cache"], "llm/trim")
    digest = cachemod.key(TRIM_SYSTEM, user, config["llm"]["model"])
    cached = store.get_json(digest)
    trim = Trim.model_validate(cached) if cached is not None else structured(Trim, TRIM_SYSTEM, user, config, log, check)
    store.put_json(digest, trim.model_dump())
    rows = []
    for cut in trim.cuts:
        full = sum(seconds[i] for i in cut.sentence_ids)
        if cut.action == "删除":
            saves = full
        else:
            original = sum(len(next(s["text"] for s in sentences if s["id"] == i)) for i in cut.sentence_ids)
            saves = max(0.0, full * (1 - len(cut.suggestion) / max(1, original)))
        rows.append({**cut.model_dump(), "saves_s": round(saves, 1),
                     "text": "".join(next(s["text"] for s in sentences if s["id"] == i) for i in cut.sentence_ids)})
    return rows


# ---------------------------------------------------------------- collect
def _sentences(timeline: dict) -> list[dict]:
    return [{"id": s["id"], "text": s["text"]} for s in timeline["sentences"]]


def contact_times(storyboard: dict, lang: str, total: float) -> list[tuple[str, float]]:
    """One frame per scene, taken just before its end so every reveal is visible."""
    times = [(s["id"], max(s["start"] + 0.1, s["end"] - 0.45)) for s in storyboard["timing"][lang]]
    first = storyboard["timing"][lang][0]["start"]
    if first > 0:  # the video opens on its cover
        times.insert(0, ("cover", first / 2))
    last = storyboard["timing"][lang][-1]["end"]
    return times + [("end", last + (total - last) / 2)]  # middle of the end card, not inside the fade-out


def collect(out: Path, config: dict, log=None) -> dict:
    """Run every check; returns a dict the markdown writer (and tests) use."""
    build = out / "build"
    stats = json.loads((build / "render_stats.json").read_text(encoding="utf-8"))
    storyboard = json.loads((out / "storyboard.json").read_text(encoding="utf-8"))
    timelines = {lang: json.loads((build / f"timeline_{lang}.json").read_text(encoding="utf-8")) for lang in ("zh", "en")}
    fps = config["video"]["fps"]
    from ..render.theme import font_path

    sub_fonts = {"zh": font_path("Noto Sans CJK SC", "bold"), "en": font_path("Inter", "bold")}

    outputs = {}
    for filename, info in stats["outputs"].items():
        name, platform = PLATFORM[filename]
        lang = "zh" if filename.startswith("zh") else "en"
        video = out / filename
        size = (1920, 1080) if "16x9" in info["variant"] else (1080, 1920)
        result = [checks.duration(name, info["duration"], config, platform),
                  checks.streams(name, video, {"size": size, "fps": fps, "artwork": True}),
                  checks.subtitle_sync(name, timelines[lang]),
                  checks.layout(name, info),
                  checks.glyphs(name, info, {"subtitle": sub_fonts[lang]}),
                  checks.loudness(name, video),
                  checks.clipping(name, build / f"mix_{lang}" / "final_mix.wav"),
                  checks.dead_air(name, build / f"{lang}.wav", timelines[lang])]
        scaled = [s for s in info["scenes"] if s.get("scale", 1.0) < 1.0]
        if scaled:
            result.append(Check("ok", f"{name} 有 {len(scaled)} 个场景文字过长，已自动缩小字号放进画面",
                                items=[f"场景 {s['id']}：缩到 {s['scale']:.0%}" for s in scaled], auto_fixed=True))
        sheet = checks.contact_sheet(video, contact_times(storyboard, lang, info["duration"]),
                                     out / f"contact_sheet_{info['variant']}.png")
        outputs[filename] = {"name": name, "duration": info["duration"], "audio": info["audio"],
                             "checks": result, "contact_sheet": sheet.name}

    covers = []
    for cover, records in stats.get("covers", {}).items():
        missing = sorted({ch for r in records for ch in missing_glyphs(r["text"], r["font"])})
        from PIL import Image

        from ..render.theme import Box

        w, h = Image.open(out / cover).size
        frame = Box(0.06 * w, 0.06 * h, 0.88 * w, 0.88 * h)
        off = [r["text"] for r in records if not frame.contains(Box(**r["box"]), 1.0)]
        if missing or off:
            covers.append(Check("error", f"封面 {cover} 有问题",
                                items=[f"缺字：{''.join(missing)}"] * bool(missing) + [f"文字出界：{t}" for t in off]))
        else:
            covers.append(Check("ok", f"封面 {cover} 文字完整、在边距内（{w}×{h}）"))

    disclaimer = stats["disclaimer"]
    findings = compliance.scan(_sentences(timelines["zh"])) + compliance.scan(_sentences(timelines["en"]))
    review_note = "仅规则扫描（非投资 / 理财类内容）"
    if disclaimer["on"]:
        try:
            findings += compliance.llm_review(_sentences(timelines["zh"]), config, log)
            review_note = "规则扫描 + Claude 逐句复核"
        except Exception as exc:  # the review is an extra; the rule scan already ran
            review_note = f"规则扫描；Claude 复核失败（{type(exc).__name__}），请人工看一遍"
    seen, unique = set(), []
    for f in findings:
        if (f.sentence_id, f.quote) not in seen:
            seen.add((f.sentence_id, f.quote))
            unique.append(f)

    asr = json.loads((build / "asr_check.json").read_text(encoding="utf-8")) if (build / "asr_check.json").exists() else {}
    changes = json.loads((build / "zh_changes.json").read_text(encoding="utf-8")) if (build / "zh_changes.json").exists() else []

    # cuts are suggested on the Chinese original (the English is adapted from it) when either version runs long
    trims = {}
    limit = config["duration"]["target_max_s"]
    longest = max(t["duration"] for t in timelines.values())
    if longest > limit:
        # the same share has to come out of the Chinese for the longer (usually English) version to fit
        target = timelines["zh"]["duration"] * limit / longest
        try:
            trims["zh"] = trim_suggestions(timelines["zh"], target, config, log)
        except Exception as exc:  # suggestions are advisory; the report must still be written
            trims["zh"] = [{"error": f"{type(exc).__name__}: {exc}"}]

    autofix = [e for e in (log.events if log else []) if e.get("autofix")]
    return {"outputs": outputs, "covers": covers, "findings": unique, "review_note": review_note,
            "disclaimer": disclaimer, "asr": asr, "changes": changes, "trims": trims, "autofix": autofix,
            "storyboard": storyboard, "timelines": timelines}


# ---------------------------------------------------------------- attention list
def attention(data: dict) -> list[tuple[str, str]]:
    """(level, text) items for the top of the report, most severe first."""
    items: list[tuple[str, str]] = []
    for out in data["outputs"].values():
        for c in out["checks"]:
            if c.level in ("error", "warn"):
                items.append((c.level, c.title + (f"：{'；'.join(c.items[:3])}" if c.items else "")))
    for c in data["covers"]:
        if c.level != "ok":
            items.append((c.level, c.title + f"：{'；'.join(c.items[:3])}"))
    for f in data["findings"]:
        items.append(("error" if f.level == "high" else "warn",
                      f"合规（{f.category}）第 {f.sentence_id} 句“{f.quote}”：{f.reason}"))
    for lang, result in data["asr"].items():
        if result.get("flagged"):
            ids = "、".join(str(r["id"]) for r in result["flagged"])
            items.append(("warn", f"{'中文' if lang == 'zh' else '英文'}配音有 {len(result['flagged'])} 句可能读错 / "
                                  f"含糊（第 {ids} 句），请试听，详见「配音回听」"))
    if data["changes"]:
        items.append(("warn", f"中文稿为口播流畅做了 {len(data['changes'])} 处微调，请确认没有改变原意，详见「中文口播微调」"))
    d = data["disclaimer"]
    if d["source"].startswith("命令行"):
        items.append(("warn", f"免责声明按命令行强制设为{'开' if d['on'] else '关'}"))
    elif d["keyword_hits"] and not d["on"]:
        items.append(("warn", f"稿件含金融词（{'、'.join(d['keyword_hits'][:5])}）但未加免责声明，请确认"))
    order = {"error": 0, "warn": 1}
    return sorted(items, key=lambda x: order[x[0]])


# ---------------------------------------------------------------- markdown
def markdown(data: dict, title: str) -> str:
    lines = [f"# 制作报告：{title}", "", f"生成时间：{datetime.now():%Y-%m-%d %H:%M}　·　所有文件只在本地，未上传或发布。", ""]

    lines += ["## 需要你重点看的地方", ""]
    items = attention(data)
    if not items:
        lines.append("✅ 自动检查没有发现问题。发布前照常完整看一遍两个成片即可。")
    for level, text in items:
        lines.append(f"- {ICON[level]} {text}")
    errors = sum(1 for level, _ in items if level == "error")
    lines += ["", f"🔴 = 发布前必须处理（{errors} 项）　🟡 = 请看一眼再决定（{len(items) - errors} 项）", ""]

    lines += ["## 成片一览", "", "| 文件 | 版本 | 时长 | 响度 | 真峰值 | 关键帧总览 |", "|---|---|---|---|---|---|"]
    for filename, out in data["outputs"].items():
        a = out["audio"]
        lines.append(f"| `{filename}` | {out['name']} | {out['duration']:.1f}s | {a['final_lufs']:.1f} LUFS | "
                     f"{a['peak_dbtp']:.1f} dBTP | `{out['contact_sheet']}` |")
    lines.append("")

    lines += ["## 自动检查", ""]
    for out in data["outputs"].values():
        lines += [f"### {out['name']}", ""]
        for c in out["checks"]:
            lines.append(f"- {ICON[c.level]} {c.title}" + (f"　{c.detail}" if c.detail else ""))
            lines += [f"    - {item}" for item in c.items]
        lines.append("")
    lines += ["### 封面", ""] + [f"- {ICON[c.level]} {c.title}" for c in data["covers"]] + [""]

    lines += ["## 合规扫描", "", f"方式：{data['review_note']}。只标出、不改动原文。", ""]
    if data["findings"]:
        lines += ["| 等级 | 类别 | 句子 | 原文片段 | 原因 | 来源 |", "|---|---|---|---|---|---|"]
        for f in data["findings"]:
            lines.append(f"| {'高' if f.level == 'high' else '中'} | {f.category} | {f.sentence_id} | {f.quote} | "
                         f"{f.reason} | {'规则' if f.source == 'rule' else 'Claude'} |")
    else:
        lines.append("✅ 没有发现保证收益、价格预测、买卖指令、诱导话术等高风险表述。")
    lines.append("")

    lines += ["## 中文口播微调", ""]
    if data["changes"]:
        lines.append("以下句子为了读起来顺口做了轻微调整（核心观点未改），不同意可以在原稿里改回并重跑：")
        lines.append("")
        lines += [f"- 第 {c['id']} 句：“{c['before']}” → “{c['after']}”" + (f"（{c['reason']}）" if c["reason"] else "")
                  for c in data["changes"]]
    else:
        lines.append("中文稿与原稿一致，没有改动。")
    lines.append("")

    lines += ["## 配音回听（Whisper 转写比对）", ""]
    for lang, result in data["asr"].items():
        label = "中文" if lang == "zh" else "英文"
        lines.append(f"- {label}：整体错误率 {result['overall_error_rate']:.1%}，需要试听的 {len(result['flagged'])} 句")
        for row in result["flagged"]:
            lines.append(f"    - 第 {row['id']} 句（{row['error_rate']:.0%}）原文“{row['text']}” / 听到“{row['heard']}”")
    if any(r.get("flagged") for r in data["asr"].values()):
        lines += ["", "Whisper 自己也会写错同音字，被标出的句子不一定真的读错。若确实读错，可在 "
                      "`config/zh_pronunciation.yaml` 里指定读音后重跑。"]
    lines.append("")

    d = data["disclaimer"]
    lines += ["## 免责声明", "", f"- 结果：{'已加' if d['on'] else '未加'}（判断来源：{d['source']}）"]
    lines += [f"- {r}" for r in d["reasons"]]
    lines.append("")

    lines += ["## 自动修正过的地方", ""]
    if data["autofix"]:
        lines += [f"- [{e['stage']}] {e['message']}" for e in data["autofix"]]
    else:
        lines.append("本次运行没有触发自动修正（结果可能来自缓存，缓存的内容在当初生成时已通过同样的校验）。")
    for out in data["outputs"].values():
        for c in out["checks"]:
            if c.auto_fixed:
                lines.append(f"- {c.title}：" + "；".join(c.items))
    lines.append("")

    if data["trims"].get("zh"):
        lines += ["## 精简建议（Claude，供参考）", ""]
        rows = data["trims"]["zh"]
        if "error" in rows[0]:
            lines.append(f"生成精简建议失败：{rows[0]['error']}")
        else:
            total = sum(r["saves_s"] for r in rows)
            longest = max(t["duration"] for t in data["timelines"].values())
            zh = data["timelines"]["zh"]["duration"]
            lines.append(f"全部采纳中文约可缩短 {total:.0f} 秒（{zh:.0f}s → 约 {zh - total:.0f}s）；英文版按同样比例约 "
                         f"{longest:.0f}s → {longest * (zh - total) / zh:.0f}s。改稿后重跑即可：")
            lines.append("")
            for r in rows:
                ids = "、".join(map(str, r["sentence_ids"]))
                change = f" → “{r['suggestion']}”" if r["action"] == "缩短" and r["suggestion"] else ""
                lines.append(f"- 第 {ids} 句 {r['action']}（约省 {r['saves_s']:.1f}s）：“{r['text']}”{change}　{r['reason']}")
        lines.append("")

    lines += ["## 分镜", "", "| 场景 | 句子 | 组件 | 为什么 |", "|---|---|---|---|"]
    for s in data["storyboard"]["scenes"]:
        lines.append(f"| {s['id']} | {s['sentence_ids'][0]}–{s['sentence_ids'][-1]} | {s['component']} | {s['why']} |")
    lines.append("")
    return "\n".join(lines)


def title_of(out: Path) -> str:
    """The title an earlier report used, else the folder name."""
    report = out / "report.md"
    if report.exists():
        first = report.read_text(encoding="utf-8").splitlines()[0]
        if first.startswith("# 制作报告："):
            return first.removeprefix("# 制作报告：")
    return out.name


def write(out: Path, config: dict, title: str, log=None) -> dict:
    data = collect(out, config, log)
    (out / "report.md").write_text(markdown(data, title), encoding="utf-8")
    return data
