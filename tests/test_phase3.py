from pathlib import Path

import pytest

from vagent.plan.schema import Storyboard, problems
from vagent.script.classify import decide_disclaimer

ZH = {1: "你的目标是不是太大了？", 2: "真正留下来的是小习惯。", 3: "比特币过去十年涨了 100 倍。", 4: "第一，每天读一页。"}
EN = {1: "Is your goal too big?", 2: "Small habits are what stick.", 3: "Bitcoin went up 100x in ten years.",
      4: "One: read a page a day."}
TIMES = {1: (0.3, 2.4), 2: (2.8, 4.9), 3: (5.3, 8.0), 4: (8.4, 9.6)}


def board(scenes, **extra):
    data = {"content_type": "mindset", "disclaimer": {"on": False, "reason": "life advice"},
            "hook_sentence_id": 2, "scenes": scenes}
    data.update(extra)
    return Storyboard.model_validate(data)


def hook(ids=(1, 2)):
    return {"id": "s01", "sentence_ids": list(ids), "component": "hook",
            "params_zh": {"text": "留下来的是小习惯"}, "params_en": {"text": "Small habits stick"}}


def keyword(sid, ids, zh="读书", en="Reading"):
    return {"id": sid, "sentence_ids": list(ids), "component": "keyword",
            "params_zh": {"word": zh}, "params_en": {"word": en}}


def good_scenes():
    return [hook(), {"id": "s02", "sentence_ids": [3], "component": "big_number",
                     "params_zh": {"value": "100 倍", "value_source_sentence": 3, "caption": "十年"},
                     "params_en": {"value": "100x", "value_source_sentence": 3, "caption": "ten years"}},
            keyword("s03", [4])]


def test_valid_storyboard_has_no_problems():
    assert problems(board(good_scenes()), ZH, EN, TIMES) == []


def test_first_scene_must_be_a_hook_lasting_three_seconds():
    scenes = good_scenes()
    scenes[0] = hook(ids=(1,))
    scenes[1]["sentence_ids"] = [2, 3]
    assert any("lasts >= 3s" in p or "covers only" in p for p in problems(board(scenes), ZH, EN, TIMES))
    scenes = good_scenes()
    scenes[0]["component"] = "keyword"
    scenes[0]["params_zh"], scenes[0]["params_en"] = {"word": "你"}, {"word": "You"}
    assert any("first scene must use the 'hook'" in p for p in problems(board(scenes), ZH, EN, TIMES))


def test_every_sentence_exactly_once_and_in_order():
    scenes = good_scenes()
    scenes[2]["sentence_ids"] = [3, 4]
    found = problems(board(scenes), ZH, EN, TIMES)
    assert any("repeated [3]" in p for p in found)
    scenes = [hook(ids=(1,)), keyword("s02", [2]), good_scenes()[1]]  # nothing covers sentence 4
    assert any("missing [4]" in p for p in problems(board(scenes), ZH, EN, TIMES))


def test_data_red_line_rejects_numbers_not_in_the_script():
    scenes = good_scenes()
    scenes[1]["params_zh"]["value"] = "200 倍"
    found = problems(board(scenes), ZH, EN, TIMES)
    assert any("200" in p and "data red line" in p for p in found)
    scenes = good_scenes()
    scenes[2] = {"id": "s03", "sentence_ids": [4], "component": "trend",
                 "params_zh": {"direction": "up", "values": [1, 5, 9]}, "params_en": {"direction": "up"}}
    assert any("does not appear" in p for p in problems(board(scenes), ZH, EN, TIMES))


def test_component_params_and_languages_are_validated():
    scenes = good_scenes()
    scenes[2]["params_en"] = {"word": "底线"}
    assert any("params_en contains Chinese" in p for p in problems(board(scenes), ZH, EN, TIMES))
    scenes = good_scenes()
    scenes[2]["params_zh"] = {"caption": "缺少 word"}
    assert any("params_zh invalid for keyword" in p for p in problems(board(scenes), ZH, EN, TIMES))


def test_no_component_three_times_in_a_row():
    zh = {i: f"第{i}句话。" for i in range(1, 6)}
    en = {i: f"Line {i}." for i in range(1, 6)}
    times = {i: (i - 1.0, i - 0.2) for i in range(1, 6)}
    times[1] = (0.0, 3.5)
    scenes = [hook(ids=(1,)), keyword("s02", [2]), keyword("s03", [3]), keyword("s04", [4]), keyword("s05", [5])]
    scenes[0]["params_zh"], scenes[0]["params_en"] = {"text": "第一句"}, {"text": "First"}
    assert any("3 times in a row" in p for p in problems(board(scenes, hook_sentence_id=1), zh, en, times))


FIXTURE = Path(__file__).parent / "fixtures/small_habits.txt"


def test_disclaimer_off_for_a_life_mindset_script():
    decision = decide_disclaimer(FIXTURE.read_text(encoding="utf-8"), "mindset")
    assert decision["on"] is False
    assert decision["keyword_hits"] == []


@pytest.mark.parametrize("text", [
    "长期定投指数基金，比短线炒股更容易获得复利。",
    "比特币减半之后，很多人开始囤币。",
    "Bitcoin is a long-term bet, not a trade.",
])
def test_disclaimer_on_for_finance_and_crypto(text):
    assert decide_disclaimer(text, None)["on"] is True


def test_llm_type_and_override():
    assert decide_disclaimer("把钱放在哪里，决定了十年后的你。", "personal_finance")["on"] is True
    assert decide_disclaimer("比特币减半之后，很多人开始囤币。", "crypto", override="off")["on"] is False
    assert decide_disclaimer("心态比技巧重要。", "mindset", override="on")["on"] is True


def test_number_words_count_as_stated_numbers():
    from vagent.plan.schema import source_numbers

    assert {"3", "10"} <= source_numbers("如果你只想拿三个月，愿意拿十年")
    assert {"3", "10"} <= source_numbers("Three months? Ten years?")
    assert "200" not in source_numbers("比特币过去十年涨了 100 倍。")


def test_localize_keeps_original_when_only_punctuation_differs(tmp_path, monkeypatch):
    from vagent.script import localize as loc
    from vagent.script.parse import split

    script = split("投资收益，应该来自价值创造\n现在是不是该买入？\n短期价格很难预测。")
    answer = loc.Localized(
        zh=[loc.ZhLine(id=1, text="投资收益,应该来自价值创造。"), loc.ZhLine(id=2, text="现在是不是该买入?"),
            loc.ZhLine(id=3, text="短期价格,真的很难预测.", change_reason="加强语气停顿")],
        en=[loc.EnLine(id=i, text=t) for i, t in ((1, "Returns."), (2, "Buy now?"), (3, "Hard to call."))])
    monkeypatch.setattr(loc, "structured", lambda *a, **k: answer)
    zh, _, changes = loc.localize(script, {"paths": {"cache": str(tmp_path)}, "llm": {"model": "m"}})
    assert [s.text for s in zh.sentences[:2]] == ["投资收益，应该来自价值创造", "现在是不是该买入？"]
    assert zh.sentences[2].text == "短期价格，真的很难预测。"          # a real edit, punctuation normalised
    assert [c["id"] for c in changes] == [3]
