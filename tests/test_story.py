"""Story mode: subtitle layout and timing rules that are easy to break."""
import cairo

from story.render import wrap
from story.stage import text_width


def _ctx():
    return cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 10, 10))


def test_every_subtitle_row_fits_the_screen():
    """A long English line on the narrow portrait frame must wrap into rows that each fit, never spill off."""
    cr, size, max_w = _ctx(), 58, 1080 * 0.76
    for line in ["Every evening the old lighthouse keeper climbed the stairs to check the lamp",
                 "Because the road was long she packed water bread and a small lantern for the night",
                 "周末的早上 我们一起去公园散步 顺便买了一束花 回家路上又遇到了老朋友"]:
        rows = wrap(cr, line, size, max_w)
        assert all(text_width(cr, row, size) <= max_w for row in rows), rows
        assert "".join(rows).replace(" ", "") == line.replace(" ", "")


def test_wrap_keeps_title_marks_together():
    cr = _ctx()
    rows = wrap(cr, "他在《小王子》里读到一句话", 58, 1080 * 0.4)
    assert all(row.count("《") == row.count("》") for row in rows), rows


def test_long_english_lines_become_shorter_subtitles():
    """A long English sentence is shown in parts, one after another, not as one block of text."""
    from story.narrate import _subtitles

    text = "Every evening the old lighthouse keeper climbed the long stairs, lit the lamp and watched the sea."
    char_time = {c: c * 0.06 for c in range(len(text) + 1)}
    subs = _subtitles(text, 0, len(text), char_time, None, "en")
    assert all(len(s["text"]) <= 48 for s in subs), [s["text"] for s in subs]
    assert " ".join(s["text"] for s in subs).replace(",", "") == text.rstrip(".").replace(",", "")
    assert all(a["end"] <= b["start"] for a, b in zip(subs, subs[1:]))


def test_space_joining_english_shots_is_not_a_subtitle():
    """English shots are joined with a space; that space must not become an empty, negative-length subtitle."""
    from story.narrate import _subtitles

    text = "When was the last time someone changed your mind? If you can't remember, that's normal."
    b = text.index("If")                     # the first shot is [0, b), its trailing space included
    char_time = {c: c * 0.06 for c in range(len(text) + 1)}
    subs = _subtitles(text, 0, b, char_time, None, "en")
    assert all(s["text"] and s["end"] > s["start"] for s in subs), subs


def test_wrap_breaks_where_a_reader_pauses():
    """Two-row Chinese subtitles break at a pause or before a quote, never inside a number word like 双十一."""
    cr, size, max_w = _ctx(), 58, 1080 * 0.76
    rows = wrap(cr, "这件外套是我去年双十一在网上买的", size, max_w)
    assert any("双十一" in r for r in rows), rows
    rows = wrap(cr, "你的书架上哪本书经得起这句“再读一遍”？", size, max_w)
    assert len(rows) == 1 or rows[1].startswith("“") or rows[0].endswith("，"), rows


def test_english_colons_do_not_cut_a_sentence():
    """'Two: ask yourself...' is one spoken sentence; cutting at the colon voices 'Two:' alone."""
    from story.narrate import sentence_spans

    text = "So try three things. One: ask yourself, would I buy it at full price? Two: wait a day."
    pieces = [text[a:b].strip() for a, b in sentence_spans(text, "en")]
    assert pieces == ["So try three things.", "One: ask yourself, would I buy it at full price?", "Two: wait a day."]


def test_constellation_words_never_overlap():
    """Star-traced words get room for their real width: "EGO" and "BLIND SPOT" overlapped in a fixed-width slot."""
    from types import SimpleNamespace

    from story.scenes.constellation import _layout

    cr = _ctx()
    for portrait in (False, True):
        st = SimpleNamespace(W=1080 if portrait else 1920, H=1920 if portrait else 1080, u=1.0, portrait=portrait)
        for figures in (["EGO", "BLIND SPOT"], ["自我", "盲点"], ["crack", "+", "lamp", "=", "spiral"]):
            size, centers = _layout(cr, st, figures)
            boxes = [(cx - w / 2, cx + w / 2) for cx, w in
                     ((cx, text_width(cr, f, size * 0.9) if len(f) > 1 and f not in ("crack", "lamp", "spiral")
                       else size) for cx, f in zip(centers, figures))]
            assert all(a[1] < b[0] for a, b in zip(boxes, boxes[1:])), (figures, boxes)
            assert boxes[0][0] >= 0 and boxes[-1][1] <= st.W, (figures, boxes)


def test_struck_out_view_and_its_replacement_fit_the_screen():
    """The old view, its strike line and the new gold view stay on screen, even for long English phrases."""
    from types import SimpleNamespace

    from story.scenes.strike import layout

    cr = _ctx()
    for portrait in (False, True):
        st = SimpleNamespace(W=1080 if portrait else 1920, H=1920 if portrait else 1080, u=1.0, portrait=portrait)
        for params in ({"old": "犯错=我不行", "new": "错误=学费"},
                       {"old": "A mistake means I'm not good enough", "new": "Every mistake is tuition"}):
            size, cx, _, _ = layout(cr, st, params)
            half = max(text_width(cr, params["old"], size) / 2 + size * 0.2, text_width(cr, params["new"], size, 1) / 2)
            assert cx - half >= 0 and cx + half <= st.W, (params, size)


def test_opposite_lights_on_the_ring_meet_at_the_top_and_labels_fit():
    """Leaving the bottom of the ring in opposite directions, the two lights end at the same point, at the top."""
    from types import SimpleNamespace

    from story.scenes.ring_meet import heads, label_size, ring

    cr = _ctx()
    for portrait in (False, True):
        st = SimpleNamespace(W=1080 if portrait else 1920, H=1920 if portrait else 1080, u=1.0, portrait=portrait)
        cx, cy, r = ring(st)
        (lx, ly), (rx, ry) = heads(st, 0.0)
        assert abs(lx - rx) < 1e-6 and abs(ly - (cy + r)) < 1e-6
        (lx, ly), (rx, ry) = heads(st, 0.5)
        assert lx < cx < rx
        (lx, ly), (rx, ry) = heads(st, 1.0)
        assert abs(lx - rx) < 1e-6 and abs(ly - (cy - r)) < 1e-6 and cy - r > 0
        words = ["Forward to the frontier", "Back to the source"]
        size = label_size(cr, st, words)
        assert max(text_width(cr, w, size) for w in words) <= cx - r - 24, (portrait, size)


def test_a_title_line_without_punctuation_ends_its_own_sentence():
    """A shot whose narration ends with a line break (a title line with no full stop) is said as its own sentence,
    not run on into the next line; a shot cut mid-sentence still joins the next one."""
    from story.narrate import sentence_spans, shot_texts

    shots = [{"narration": "阻碍财富积累的几个习惯\n"}, {"narration": "你有没有发现，存款却没多多少？"},
             {"narration": "这套系统的边际效益见顶"}, {"narration": "（甚至开始反噬人本身）。"}]
    full = "".join(shot_texts(shots, "zh"))
    said = [full[a:b].strip() for a, b in sentence_spans(full, "zh")]
    assert said == ["阻碍财富积累的几个习惯", "你有没有发现，存款却没多多少？", "这套系统的边际效益见顶（甚至开始反噬人本身）。"]


def test_a_short_line_on_a_slow_scene_is_reported_as_a_wait(tmp_path):
    """When a shot's picture needs longer than its voice, the voice waits in silence; the draft names that shot so
    it can be merged with its neighbour before rendering (a 2-second gap mid-thought sounds like a stall)."""
    from story.narrate import narrate, waits

    config = {"tts": {"zh": {"speed": 1.0, "voice": "x"}, "pause_s": {"sentence": 0.38, "question": 0.5,
                                                                     "colon": 0.3, "paragraph": 0.7}},
              "paths": {"models": str(tmp_path), "cache": str(tmp_path)}}
    shots = [{"id": 1, "act": "a", "narration": "可你得问问自己：", "scene": "mirror", "params": {}},
             {"id": 2, "act": "a", "narration": "这笔钱，是为了让我过得舒服，还是为了让别人觉得我过得不错？",
              "scene": "fork", "params": {}},
             {"id": 3, "act": "a", "narration": "别人的一句话，不值得你每个月都为它买单，也不值得你一直惦记。",
              "scene": "walk", "params": {}}]
    _, timeline = narrate({"shots": shots}, config, draft=True)
    assert [w["id"] for w in waits(timeline)] == [1]
    assert waits(timeline)[0]["wait_s"] > 1.0


def test_section_headings_in_brackets_are_not_narration():
    """A line like 【第一步：明确目标】 is a heading for the reader: shots that leave it out still match the script."""
    from story.narrate import check_script

    script = "开头一句。\n【第一步：明确目标】\n达利欧说，第一步，先搞清楚你到底要什么。\n"
    check_script({"shots": [{"narration": "开头一句。"}, {"narration": "达利欧说，第一步，先搞清楚你到底要什么。"}]}, script)
