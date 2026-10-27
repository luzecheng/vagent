import re

import numpy as np
import pytest

from vagent import config as configmod
from vagent.script import parse
from vagent.subtitles import segment
from vagent.tts.base import SR, proportional_timings

CONFIG = configmod.load()


def test_split_sentences_and_kinds():
    script = parse.split("你以为？\n可最后，还是你自己。\n问问自己：\n这条路对吗？")
    assert [s.text for s in script.sentences] == ["你以为？", "可最后，还是你自己。", "问问自己：", "这条路对吗？"]
    assert [s.kind for s in script.sentences] == ["question", "statement", "lead", "question"]


def test_paragraphs_from_blank_lines():
    script = parse.split("第一段。第一段第二句。\n\n第二段。")
    assert [s.paragraph for s in script.sentences] == [0, 0, 1]
    assert [s.ends_paragraph for s in script.sentences] == [False, True, True]


def test_clean_keeps_number_grouping_and_strips_markdown():
    assert parse.clean("# 标题\n**重点**：1,000 个,好") == "标题\n重点：1,000 个，好"


def test_duration_estimate_scales_with_length():
    short = parse.estimate_seconds(parse.split("一句话。"), "zh", CONFIG)
    long = parse.estimate_seconds(parse.split("一句话。" * 40), "zh", CONFIG)
    assert 0 < short < long
    rate = CONFIG["tts"]["rate"]["zh_chars_per_s"]
    assert long == pytest.approx(40 * 3 / rate + 40 * CONFIG["tts"]["pause_s"]["sentence"], rel=0.01)


@pytest.mark.parametrize("text", [
    "很多计划写在本子上的时候都很漂亮，可惜没有一个真正坚持下来的。",
    "所谓小习惯，就是把目标拆成每天都能完成的动作，把中断当成重新开始的提醒。",
    "精力总会起伏。哪怕今天很累，也能挑出最小的一步，先完成它，再想明天的事。",
])
def test_zh_lines_never_split_words_or_start_with_particles(text):
    import jieba

    words = [w for w in jieba.lcut(text) if w.strip("，。：？")]
    lines = segment.break_lines(segment.tokens(text, "zh"), "zh", 13)
    for line in lines:
        shown = segment.display(line, "zh")
        assert segment.width(shown, "zh") <= 13
        assert shown[0] not in segment.ZH_NO_LINE_START
        assert segment.display(line, "zh").replace(" ", "")  # not empty
    # every line boundary is also a jieba word boundary
    joined, boundaries = "", set()
    for line in lines:
        joined += "".join(t.text for t in line)
        boundaries.add(len(joined))
    position, word_ends = 0, set()
    for word in jieba.lcut(text):
        position += len(word)
        word_ends.add(position)
    assert boundaries <= word_ends | {len(text)}


def test_en_never_breaks_after_function_words():
    text = ("You can hand off the decision, but you can never hand off the consequences of it, "
            "and the cost of a bad call lands on you.")
    lines = segment.break_lines(segment.tokens(text, "en"), "en", 32)
    for line in lines[:-1]:
        assert line[-1].text.lower().strip(",.") not in segment.EN_FUNCTION
    for line in lines:
        assert len(segment.display(line, "en")) <= 32


def test_screens_have_at_most_two_lines_and_follow_speech():
    text = "所谓小习惯，就是把目标拆成每天都能完成的动作，把中断当成重新开始的提醒。"
    units = [u.__dict__ for u in proportional_timings(text, "zh", 1.0, 7.0)]
    sentence = {"id": 1, "text": text, "start": 1.0, "end": 7.0, "units": units}
    screens = segment.screens_for_sentence(sentence, "zh", 13)
    assert all(len(s.lines) <= 2 for s in screens)
    assert screens[0].start == pytest.approx(1.0)
    assert screens[-1].end == pytest.approx(7.0, abs=0.01)
    assert all(a.end <= b.start for a, b in zip(screens, screens[1:]))
    shown = "".join("".join(s.lines) for s in screens).replace(" ", "")
    assert shown == re.sub(r"[，。]", "", text)


@pytest.mark.parametrize("text,lang,max_chars", [
    # 3 full lines would leave "a row." alone on a second screen
    ("You can pick a different habit each month, but never skip two days in a row.", "en", 32),
    ("Your habits are yours, and you get to shape them your way, even when the people around you doubt it.", "en", 32),
    ("你可以把计划定得很宏大，却没办法每天都保持热情，最后能留下来的，还是那些小习惯。", "zh", 13),
])
def test_long_sentences_split_into_balanced_screens(text, lang, max_chars):
    units = [u.__dict__ for u in proportional_timings(text, lang, 0.0, 8.0)]
    sentence = {"id": 1, "text": text, "start": 0.0, "end": 8.0, "units": units}
    screens = segment.screens_for_sentence(sentence, lang, max_chars)
    assert len(screens) >= 2
    sizes = [segment.width(" ".join(s.lines), lang) for s in screens]
    assert min(sizes) >= 0.4 * max(sizes), screens          # no leftover fragment screen
    for s in screens:
        assert len(s.lines) <= 2
        assert all(segment.width(line, lang) <= max_chars for line in s.lines)
        if len(s.lines) == 2:                                    # no one-word stub line
            short, long_ = sorted(segment.width(line, lang) for line in s.lines)
            assert short >= 0.35 * long_, s.lines


def test_srt_format_and_no_overlap():
    screens = [segment.Screen(["一"], 0.5, 1.2, 1), segment.Screen(["二", "三"], 1.3, 2.0, 2)]
    out = segment.srt(screens)
    assert out.startswith("1\n00:00:00,500 --> 00:00:01,200\n一\n")
    assert "2\n00:00:01,300 --> 00:00:02,000\n二\n三\n" in out


def test_tone_marks():
    from vagent.tts.kokoro import tone_mark

    assert [tone_mark(s) for s in ["zhu4", "dei3", "lv4", "gui4", "liu2", "de5", "shou3"]] == \
        ["zhù", "děi", "lǜ", "guì", "liú", "de", "shǒu"]


def test_pronunciation_table_rejects_mismatched_lengths(tmp_path):
    from vagent.tts.kokoro import load_pronunciations

    good = tmp_path / "ok.yaml"
    good.write_text("守住: shou3 zhu4\n", encoding="utf-8")
    assert load_pronunciations(good) == {"守住": ["shou3", "zhu4"]}
    bad = tmp_path / "bad.yaml"
    bad.write_text("守住: shou3\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_pronunciations(bad)


def test_asr_error_rate():
    from vagent.qa.asr import error_rate

    assert error_rate("每天读书", "每天读书", "zh") == 0
    assert error_rate("每天读书", "美甜读书", "zh") == pytest.approx(0.5)
    assert error_rate("Hold the line.", "hold the line", "en") == 0


def test_fresh_and_cached_narration_are_identical(tmp_path):
    """Checks keyed on the audio (e.g. the Whisper round trip) must hit their cache on the second run."""
    import numpy as np

    from vagent import cache as cachemod
    from vagent.audio.narration import _synth_cached
    from vagent.tts.base import Speech, Unit

    class Fake:
        def cache_identity(self):
            return "fake"

        def synth(self, text, lang, voice, speed):
            audio = np.random.default_rng(0).uniform(-0.5, 0.5, 2400)   # float64, not 16-bit exact
            return Speech(audio, [Unit("a", 0.0, 0.1)], True, "fake", [])

    store = cachemod.Cache(str(tmp_path), "tts/zh")
    fresh = _synth_cached(Fake(), "一句话", "zh", "v", 1.0, store).audio
    cached = _synth_cached(Fake(), "一句话", "zh", "v", 1.0, store).audio
    assert fresh.dtype == cached.dtype == np.float32
    assert np.array_equal(fresh, cached)


def test_local_config_overrides_brand_and_defaults(tmp_path, monkeypatch):
    """config/local.yaml (git-ignored) holds per-machine choices such as a slower, heavier voice."""
    from vagent import config as configmod

    local = tmp_path / "local.yaml"
    local.write_text("tts:\n  zh: {provider: cosyvoice, voice: 'sft:中文男'}\n", encoding="utf-8")
    config = configmod.load(local_path=local)
    assert config["tts"]["zh"]["provider"] == "cosyvoice" and config["tts"]["zh"]["voice"] == "sft:中文男"
    assert config["tts"]["en"]["provider"] == "kokoro"                       # untouched keys survive
    assert configmod.load(local_path=tmp_path / "missing.yaml")["tts"]["zh"]["provider"] == "kokoro"
    assert configmod.load({"tts": {"zh": {"voice": "x"}}}, local_path=local)["tts"]["zh"]["voice"] == "x"  # CLI wins


def test_spoken_text_reads_math_symbols_aloud_in_chinese():
    # CosyVoice skips "+" and garbles "=" (seen: "梦想C时现实C位决心空"), so zh narration spells them out
    formula = "他给过一个公式：梦想 + 现实 + 决心 = 成功的人生。"
    assert parse.spoken_text(formula, "zh") == "他给过一个公式：梦想加现实加决心等于成功的人生。"
    assert parse.spoken_text("一＋一＝二", "zh") == "一加一等于二"
    assert parse.spoken_text("dreams + reality = a successful life", "en") == "dreams + reality = a successful life"
    assert parse.spoken_text("“享受”", "zh") == "享受"


def test_spoken_text_spells_out_capital_letter_acronyms_in_chinese():
    # CosyVoice reads a run of capitals as one word ("用AI" came out as "用爱"); spaced, it says each letter
    assert parse.spoken_text("就是学会用 AI。", "zh") == "就是学会用 A I。"
    assert parse.spoken_text("借助AI，做出了工具", "zh") == "借助A I，做出了工具"
    assert parse.spoken_text("问问CEO和PPT", "zh") == "问问C E O和P P T"
    assert parse.spoken_text("iPhone 和 Excel 不变", "zh") == "iPhone 和 Excel 不变"  # not acronyms
    assert parse.spoken_text("ABCDEF 太长不拆", "zh") == "ABCDEF 太长不拆"
    assert parse.spoken_text("Learn to use AI.", "en") == "Learn to use AI."


def test_spoken_text_turns_a_chinese_dash_into_a_pause():
    # CosyVoice voiced "——" as a syllable (heard "心里还在说虚应该")
    assert parse.spoken_text("心里还在说——不应该啊。", "zh") == "心里还在说，不应该啊。"
    assert parse.spoken_text("心里还在说--不应该啊。", "zh") == "心里还在说，不应该啊。"
    assert parse.spoken_text("我们——包括你——都一样", "zh") == "我们，包括你，都一样"
    assert parse.spoken_text("2020-2021", "zh") == "2020-2021"


def test_audio_check_compares_against_what_was_meant_to_be_spoken(monkeypatch):
    from vagent.qa import audio_check

    monkeypatch.setattr(audio_check, "transcribe", lambda *a: "梦想加现实加决心等于成功的人生")
    timeline = {"sentences": [{"id": 1, "text": "梦想 + 现实 + 决心 = 成功的人生", "clip_start": 0, "clip_end": 1}]}
    result = audio_check.check(np.zeros(SR, np.float32), timeline, "zh")
    assert result["flagged"] == []


def test_a_line_ending_in_a_comma_continues_on_the_next_line():
    # each sentence is voiced on its own; a clause cut at a line break was read with a final cadence
    raw = "开头一句。\n\n没有必要通过一个住址，\n向谁证明自己过得好。\n\n我们生活中有多少选择，\n都像租房一样？\n我给自己写下一条原则：\n做一个超级现实的人。"
    texts = [s.text for s in parse.split(raw).sentences]
    assert texts == ["开头一句。", "没有必要通过一个住址，向谁证明自己过得好。", "我们生活中有多少选择，都像租房一样？",
                     "我给自己写下一条原则：", "做一个超级现实的人。"]
    assert [s.text for s in parse.split("第一行，\n第二行。\n第三行。").sentences] == ["第一行，第二行。", "第三行。"]
