"""Automatic checks on the finished outputs. Each returns Check(level, title, detail).

level: "ok" | "warn" (look at it) | "error" (must fix before publishing)
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import soundfile as sf

from ..render.theme import Box, variant as make_variant
from .layout import missing_glyphs


@dataclass
class Check:
    level: str
    title: str
    detail: str = ""
    items: list[str] = field(default_factory=list)
    auto_fixed: bool = False


def _probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


# ---------------------------------------------------------------- duration
def duration(name: str, seconds: float, config: dict, platform: str) -> Check:
    limits = config["duration"]
    if platform == "x" and seconds > 140:
        return Check("error", f"{name} 时长 {seconds:.1f}s 超过 X 非会员上限 2:20",
                     "非 Premium 账号无法上传；需精简或分集，或用会员账号发布。")
    if platform == "x" and seconds > 130:
        return Check("warn", f"{name} 时长 {seconds:.1f}s，接近 X 非会员上限 2:20",
                     "能上传，但几乎没有余量；见下方「精简建议」。")
    if seconds > limits["hard_cap_s"]:
        return Check("warn", f"{name} 时长 {seconds:.1f}s 超过 {limits['hard_cap_s']}s 硬上限（已按 --allow-long 制作）")
    if seconds > limits["target_max_s"]:
        return Check("warn", f"{name} 时长 {seconds:.1f}s 偏长（目标 {limits['target_min_s']}–{limits['target_max_s']}s）",
                     "见下方「精简建议」。")
    if seconds < limits["target_min_s"]:
        return Check("warn", f"{name} 时长 {seconds:.1f}s 偏短（目标至少 {limits['target_min_s']}s）")
    return Check("ok", f"{name} 时长 {seconds:.1f}s，在目标范围内")


# ---------------------------------------------------------------- streams / sync
def streams(name: str, path: Path, expected: dict) -> Check:
    info = _probe(path)
    video = next(s for s in info["streams"] if s["codec_type"] == "video"
                 and not s.get("disposition", {}).get("attached_pic"))
    artwork = [s for s in info["streams"] if s.get("disposition", {}).get("attached_pic")]
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    problems = []
    if (int(video["width"]), int(video["height"])) != expected["size"]:
        problems.append(f"分辨率 {video['width']}×{video['height']}，应为 {expected['size'][0]}×{expected['size'][1]}")
    if video["codec_name"] != "h264" or video.get("pix_fmt") != "yuv420p":
        problems.append(f"视频编码 {video['codec_name']}/{video.get('pix_fmt')}，应为 h264/yuv420p")
    num, den = (int(x) for x in video["r_frame_rate"].split("/"))
    fps = num / den
    if abs(fps - expected["fps"]) > 0.01:
        problems.append(f"帧率 {fps:g}，应为 {expected['fps']}")
    if audio is None or audio["codec_name"] != "aac":
        problems.append("缺少 AAC 音轨")
    else:
        gap = abs(float(video["duration"]) - float(audio["duration"]))
        if gap > 0.1:
            problems.append(f"音视频轨长度相差 {gap:.2f}s")
    if expected.get("artwork") and not artwork:
        problems.append("文件里没有嵌入封面图")
    if problems:
        return Check("error", f"{name} 文件规格不符", items=problems)
    art = "，已嵌入封面图" if artwork else ""
    return Check("ok", f"{name} 规格正确（{video['width']}×{video['height']}，{fps:g}fps，H.264 + AAC，音画等长{art}）")


def subtitle_sync(name: str, timeline: dict, tolerance: float = 0.2) -> Check:
    """Every subtitle screen must contain the speech it shows; first/last screens match speech start/end."""
    screens = timeline["screens"]
    units = [u for s in timeline["sentences"] for u in s["units"]]
    problems = []
    if not screens or not units:
        return Check("error", f"{name} 字幕或配音时间轴为空")
    if abs(screens[0]["start"] - units[0]["start"]) > tolerance:
        problems.append(f"首条字幕 {screens[0]['start']:.2f}s，配音开始 {units[0]['start']:.2f}s")
    if screens[-1]["end"] < units[-1]["end"] - 0.05 or screens[-1]["end"] > units[-1]["end"] + 1.0:
        problems.append(f"末条字幕结束 {screens[-1]['end']:.2f}s，配音结束 {units[-1]['end']:.2f}s")
    spoken = {s["id"]: (s["start"], s["end"]) for s in timeline["sentences"]}
    for screen in screens:
        start, end = spoken[screen["sentence_id"]]
        if screen["start"] < start - tolerance or screen["start"] > end or screen["end"] < start:
            problems.append(f"“{''.join(screen['lines'])[:14]}” 显示于 {screen['start']:.2f}–{screen['end']:.2f}s，"
                            f"但这句在 {start:.2f}–{end:.2f}s 说出")
    for prev, nxt in zip(screens, screens[1:]):
        if nxt["start"] < prev["end"] - 1e-3:
            problems.append(f"字幕重叠：{''.join(prev['lines'])[:12]}… / {''.join(nxt['lines'])[:12]}…")
    exact = sum(1 for s in timeline["sentences"] if s.get("exact"))
    method = "引擎逐音素时长" if exact == len(timeline["sentences"]) else "Whisper 强制对齐"
    if problems:
        return Check("error", f"{name} 字幕与配音不同步", items=problems)
    return Check("ok", f"{name} 字幕与配音同步（{len(screens)} 屏，时间来自 {method}）")


# ---------------------------------------------------------------- layout / glyphs
def layout(name: str, stats: dict) -> Check:
    size = (1920, 1080) if "16x9" in stats["variant"] else (1080, 1920)
    v = make_variant(stats["variant"], *size)
    problems = []
    for scene in stats["scenes"]:
        for text, box, _, _ in scene["records"]:
            if not v.content.contains(Box(**box), 1.0):
                problems.append(f"场景 {scene['id']} 文字越出画面区：{text[:20]}")
            elif not v.safe.contains(Box(**box), 1.0):
                problems.append(f"场景 {scene['id']} 文字越出安全区：{text[:20]}")
    for sub in stats["subtitles"]:
        if not v.safe.contains(Box(**sub["box"]), 1.0):
            problems.append(f"字幕越出安全区：{''.join(sub['lines'])[:20]}")
    if problems:
        return Check("error", f"{name} 有文字超出安全区", items=problems[:10])
    note = "（视频号版已避开右侧与底部按钮区）" if stats["variant"] == "zh_shipinhao" else ""
    return Check("ok", f"{name} 所有文字都在安全区内{note}")


def glyphs(name: str, stats: dict, theme_fonts: dict[str, str]) -> Check:
    missing: dict[str, set] = {}
    for scene in stats["scenes"]:
        for text, _, font, _ in scene["records"]:
            for ch in missing_glyphs(text, font):
                missing.setdefault(ch, set()).add(f"场景 {scene['id']}")
    for sub in stats["subtitles"]:
        for ch in missing_glyphs("".join(sub["lines"]), theme_fonts["subtitle"]):
            missing.setdefault(ch, set()).add("字幕")
    if missing:
        return Check("error", f"{name} 有字体缺字（会显示为豆腐块）",
                     items=[f"“{ch}” 出现在 {'、'.join(sorted(where))}" for ch, where in missing.items()])
    return Check("ok", f"{name} 无缺字 / 乱码")


# ---------------------------------------------------------------- audio
def _ebur128(path: Path) -> tuple[float, float]:
    text = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-filter_complex", "ebur128=peak=true", "-f", "null",
                           "-"], capture_output=True, text=True).stderr
    summary = text[text.rfind("Summary:"):]
    return (float(re.search(r"I:\s+(-?[\d.]+)", summary).group(1)),
            float(re.search(r"Peak:\s+(-?[\d.inf]+)", summary).group(1)))


def loudness(name: str, video: Path, target: float = -16.0) -> Check:
    integrated, peak = _ebur128(video)
    items = [f"响度 {integrated:.1f} LUFS（目标 {target:.0f}）", f"真峰值 {peak:.1f} dBTP"]
    if abs(integrated - target) > 1.0 or peak > -1.0:
        return Check("error", f"{name} 响度不合格", items=items)
    return Check("ok", f"{name} 响度合格：{integrated:.1f} LUFS，真峰值 {peak:.1f} dBTP")


def clipping(name: str, mix_wav: Path) -> Check:
    audio, _ = sf.read(mix_wav, dtype="float32")
    clipped = int(np.sum(np.abs(audio) >= 0.999))
    if clipped:
        return Check("error", f"{name} 有 {clipped} 个削波采样（爆音）")
    return Check("ok", f"{name} 无爆音（最高样本 {20 * np.log10(max(1e-9, float(np.max(np.abs(audio))))):.1f} dBFS）")


def dead_air(name: str, voice_wav: Path, timeline: dict, max_gap: float = 2.0) -> Check:
    """Silences inside the narration (between first and last word) longer than max_gap."""
    audio, sr = sf.read(voice_wav, dtype="float32")
    frame = int(0.02 * sr)
    usable = len(audio) // frame * frame
    rms = np.sqrt((audio[:usable].reshape(-1, frame) ** 2).mean(axis=1))
    quiet = rms < 10 ** (-45 / 20)
    first = timeline["sentences"][0]["start"]
    last = timeline["sentences"][-1]["end"]
    gaps, start = [], None
    for i, q in enumerate(quiet):
        t = i * frame / sr
        if q and start is None:
            start = t
        elif not q and start is not None:
            if t - start > max_gap and start > first and t < last:
                gaps.append((start, t))
            start = None
    if gaps:
        return Check("warn", f"{name} 配音中有 {len(gaps)} 处超过 {max_gap:.0f}s 的静音",
                     items=[f"{a:.1f}s – {b:.1f}s" for a, b in gaps])
    return Check("ok", f"{name} 配音中没有超过 {max_gap:.0f}s 的长静音")


# ---------------------------------------------------------------- keyframes
def contact_sheet(video: Path, times: list[tuple[str, float]], out: Path, columns: int = 6) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    from ..render.theme import font_path

    thumbs = []
    for label, t in times:
        frame = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                                "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, check=True).stdout
        from io import BytesIO

        img = Image.open(BytesIO(frame)).convert("RGB")
        scale = 300 / img.width
        img = img.resize((300, int(img.height * scale)))
        ImageDraw.Draw(img).text((10, 10), f"{label}  {t:.1f}s", fill=(255, 210, 90),
                                 font=ImageFont.truetype(font_path("Inter", "bold"), 20))
        thumbs.append(img)
    rows = (len(thumbs) + columns - 1) // columns
    w, h = thumbs[0].size
    sheet = Image.new("RGB", (columns * w + (columns + 1) * 8, rows * h + (rows + 1) * 8), (40, 40, 40))
    for i, img in enumerate(thumbs):
        sheet.paste(img, (8 + (i % columns) * (w + 8), 8 + (i // columns) * (h + 8)))
    sheet.save(out)
    return out
