from pathlib import Path
import subprocess

import numpy as np
import pytest
import soundfile as sf

from vagent.qa import checks, compliance
from vagent.qa.checks import Check
from vagent.qa.report import attention, markdown
from vagent.render.theme import font_path
from vagent.script import parse

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = {"duration": {"target_min_s": 60, "target_max_s": 120, "hard_cap_s": 140}}


def _sentences(name):
    return [{"id": s.id, "text": s.text} for s in parse.split((FIXTURES / name).read_text(encoding="utf-8")).sentences]


# ---------------------------------------------------------------- compliance
@pytest.mark.parametrize("name", ["small_habits.txt", "crypto_short.txt"])
def test_compliance_has_no_false_positives_on_ordinary_scripts(name):
    # the crypto script talks about holding periods and position sizing: opinion, not a call to buy
    assert compliance.scan(_sentences(name)) == []


@pytest.mark.parametrize("text,category", [
    ("这个币稳赚不赔，闭眼买就行。", "保证收益"),
    ("比特币今年必涨。", "价格预测"),
    ("我看它年底涨到 20 万美元。", "价格预测"),
    ("现在就买，别犹豫。", "买卖指令"),
    ("我已经梭哈了。", "买卖指令"),
    ("错过就没有了，跟着我上车。", "诱导话术"),
    ("一年翻 10 倍不是梦。", "收益暗示"),
    ("This is a risk-free trade.", "保证收益"),
    ("Buy now before it's too late.", "买卖指令"),
    ("Don't miss out, DM me.", "诱导话术"),
])
def test_compliance_flags_risky_wording(text, category):
    found = compliance.scan([{"id": 1, "text": text}])
    assert category in {f.category for f in found}
    assert all(f.quote in text for f in found)


def test_compliance_quotes_the_whole_phrase():
    assert [f.quote for f in compliance.scan([{"id": 1, "text": "稳赚不赔的机会"}])] == ["稳赚不赔"]


# ---------------------------------------------------------------- duration
def test_duration_levels_per_platform():
    assert checks.duration("x", 141, CONFIG, "x").level == "error"          # X refuses >2:20 for free accounts
    assert checks.duration("x", 135, CONFIG, "x").level == "warn"           # uploads, but no margin
    assert checks.duration("zh", 135, CONFIG, "shipinhao").level == "warn"  # long
    assert checks.duration("zh", 145, CONFIG, "shipinhao").level == "warn"  # allowed with --allow-long
    assert checks.duration("zh", 45, CONFIG, "shipinhao").level == "warn"   # short
    assert checks.duration("zh", 90, CONFIG, "shipinhao").level == "ok"


# ---------------------------------------------------------------- sync
def _timeline():
    return {"sentences": [
        {"id": 1, "start": 0.3, "end": 2.0, "units": [{"text": "a", "start": 0.3, "end": 2.0}]},
        {"id": 2, "start": 2.4, "end": 4.0, "units": [{"text": "b", "start": 2.4, "end": 4.0}]}],
        "screens": [{"lines": ["第一句"], "start": 0.3, "end": 2.25, "sentence_id": 1},
                    {"lines": ["第二句"], "start": 2.4, "end": 4.25, "sentence_id": 2}]}


def test_subtitle_sync_passes_when_screens_follow_speech():
    assert checks.subtitle_sync("zh", _timeline()).level == "ok"


def test_subtitle_sync_catches_a_shifted_screen():
    timeline = _timeline()
    timeline["screens"][1]["start"] = 0.5     # second line shown while the first is still being spoken
    result = checks.subtitle_sync("zh", timeline)
    assert result.level == "error"
    assert any("第二句" in item for item in result.items)


def test_subtitle_sync_catches_late_start():
    timeline = _timeline()
    timeline["screens"][0]["start"] = 1.0
    assert checks.subtitle_sync("zh", timeline).level == "error"


# ---------------------------------------------------------------- layout and glyphs
def _stats(variant, box, text="小习惯"):
    font = font_path("Noto Sans CJK SC", "bold")
    return {"variant": variant, "scenes": [{"id": "s01", "records": [[text, box, font, 60]]}],
            "subtitles": [{"lines": ["字幕"], "box": {"x": 208, "y": 1356, "w": 576, "h": 180}}]}


def test_layout_passes_inside_and_flags_text_under_shipinhao_buttons():
    assert checks.layout("zh", _stats("zh_shipinhao", {"x": 200, "y": 600, "w": 500, "h": 100})).level == "ok"
    # x 900–1000 is inside the generic safe area but under WeChat Channels' right-side buttons
    bad = checks.layout("zh", _stats("zh_shipinhao", {"x": 600, "y": 600, "w": 400, "h": 100}))
    assert bad.level == "error"
    assert checks.layout("en", _stats("en_x", {"x": 600, "y": 600, "w": 400, "h": 100})).level == "ok"


def test_layout_flags_subtitle_outside_safe_area():
    stats = _stats("zh_shipinhao", {"x": 200, "y": 600, "w": 500, "h": 100})
    stats["subtitles"][0]["box"]["y"] = 1700
    assert checks.layout("zh", stats).level == "error"


def test_glyph_check_flags_tofu():
    sub = {"subtitle": font_path("Noto Sans CJK SC", "bold")}
    box = {"x": 200, "y": 600, "w": 500, "h": 100}
    assert checks.glyphs("zh", _stats("zh_shipinhao", box), sub).level == "ok"
    bad = checks.glyphs("zh", _stats("zh_shipinhao", box, "习惯\U0001F680"), sub)
    assert bad.level == "error" and "\U0001F680" in bad.items[0]


# ---------------------------------------------------------------- audio
SR = 24000


def _voice(path, gaps=()):
    t = np.arange(10 * SR) / SR
    audio = 0.3 * np.sin(2 * np.pi * 200 * t)
    for a, b in gaps:
        audio[int(a * SR):int(b * SR)] = 0
    sf.write(path, audio.astype(np.float32), SR)
    return {"sentences": [{"start": 0.0, "end": 10.0}]}


def test_dead_air_ignores_normal_pauses_and_flags_long_silence(tmp_path):
    timeline = _voice(tmp_path / "ok.wav", gaps=[(3.0, 3.7)])
    assert checks.dead_air("zh", tmp_path / "ok.wav", timeline).level == "ok"
    timeline = _voice(tmp_path / "bad.wav", gaps=[(4.0, 7.0)])
    result = checks.dead_air("zh", tmp_path / "bad.wav", timeline)
    assert result.level == "warn" and len(result.items) == 1


def test_clipping_detection(tmp_path):
    t = np.arange(SR) / SR
    sf.write(tmp_path / "ok.wav", np.stack([0.5 * np.sin(2 * np.pi * 300 * t)] * 2, axis=1), SR)
    sf.write(tmp_path / "hot.wav", np.stack([np.clip(1.6 * np.sin(2 * np.pi * 300 * t), -1, 1)] * 2, axis=1), SR)
    assert checks.clipping("zh", tmp_path / "ok.wav").level == "ok"
    assert checks.clipping("zh", tmp_path / "hot.wav").level == "error"


def _video(path, fps, volume_db):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=black:s=1080x1920:r={fps}:d=4",
                    "-f", "lavfi", "-i", "sine=frequency=300:duration=4", "-filter:a", f"volume={volume_db}dB",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)
    return path


def test_stream_spec_and_loudness_checks(tmp_path):
    good = _video(tmp_path / "good.mp4", 30, 0)
    assert checks.streams("zh", good, {"size": (1080, 1920), "fps": 30}).level == "ok"
    wrong_fps = _video(tmp_path / "fps.mp4", 25, 0)
    assert checks.streams("zh", wrong_fps, {"size": (1080, 1920), "fps": 30}).level == "error"
    assert checks.streams("zh", good, {"size": (1920, 1080), "fps": 30}).level == "error"
    quiet = _video(tmp_path / "quiet.mp4", 30, -30)
    assert checks.loudness("zh", quiet).level == "error"


# ---------------------------------------------------------------- report
def _data(**extra):
    data = {"outputs": {"zh_shipinhao.mp4": {"name": "中文 · 视频号", "duration": 90.0,
                                             "audio": {"final_lufs": -16.0, "peak_dbtp": -3.0},
                                             "contact_sheet": "contact_sheet_zh_shipinhao.png",
                                             "checks": [Check("ok", "规格正确"), Check("warn", "时长偏长")]}},
            "covers": [Check("ok", "封面完整")], "findings": [], "review_note": "仅规则扫描",
            "disclaimer": {"on": False, "source": "自动判断", "reasons": ["关键词规则：未命中"], "keyword_hits": [],
                           "llm_type": "mindset"},
            "asr": {}, "changes": [], "trims": {}, "autofix": [],
            "storyboard": {"scenes": [{"id": "s01", "sentence_ids": [1, 2], "component": "hook", "why": "x"}]},
            "timelines": {"zh": {"duration": 90.0}, "en": {"duration": 95.0}}}
    data.update(extra)
    return data


def test_attention_puts_must_fix_items_first():
    findings = [compliance.Finding("high", "买卖指令", "现在就买", 3, "明确的买卖指令")]
    items = attention(_data(findings=findings, changes=[{"id": 2, "before": "a", "after": "b", "reason": "r"}]))
    assert items[0][0] == "error" and "现在就买" in items[0][1]
    assert {level for level, _ in items[1:]} == {"warn"}
    assert any("口播微调" in text for _, text in items)


def test_report_lists_sections_and_changes():
    text = markdown(_data(changes=[{"id": 2, "before": "一页书", "after": "一页的书", "reason": "常用写法"}],
                          autofix=[{"stage": "render", "message": "scene s03: text scaled to 80% to fit"}]), "小习惯")
    for heading in ("需要你重点看的地方", "成片一览", "自动检查", "合规扫描", "中文口播微调", "配音回听", "免责声明",
                    "自动修正过的地方", "分镜"):
        assert f"## {heading}" in text
    assert "“一页书” → “一页的书”" in text
    assert "scaled to 80%" in text
    assert "🔴 = 发布前必须处理（0 项）" in text


def test_report_says_clean_when_nothing_to_review():
    data = _data()
    data["outputs"]["zh_shipinhao.mp4"]["checks"] = [Check("ok", "规格正确")]
    assert "自动检查没有发现问题" in markdown(data, "t")


@pytest.mark.parametrize("text", ["Should I buy now?", "Is it time to sell now?", "现在要不要马上买？",
                                  "很多人问，是不是该现在就买？"])
def test_compliance_does_not_flag_questions_about_whether_to_buy(text):
    assert [f for f in compliance.scan([{"id": 1, "text": text}]) if f.category == "买卖指令"] == []


@pytest.mark.parametrize("text", ["Buy now, thank me later.", "Should you wait? No. Buy now.", "别犹豫，现在就买！"])
def test_compliance_still_flags_real_instructions(text):
    assert "买卖指令" in {f.category for f in compliance.scan([{"id": 1, "text": text}])}
