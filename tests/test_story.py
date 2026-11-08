"""Story mode: subtitle layout and timing rules that are easy to break."""
import math

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


def test_highlight_words_are_found_in_a_subtitle():
    """Keywords split a subtitle into plain and gold runs; English matches whole words, ignoring case."""
    from story.render import runs

    assert runs("你是先看机会 还是先看风险", ["机会", "风险"]) == [
        ("你是先看", False), ("机会", True), (" 还是先看", False), ("风险", True)]
    assert runs("Is it risky? Weigh the Risk first", ["risk"]) == [
        ("Is it risky? Weigh the ", False), ("Risk", True), (" first", False)]
    assert runs("没有关键词的一句", []) == [("没有关键词的一句", False)]


def test_wrap_never_splits_a_highlighted_word():
    """A gold keyword stays on one row, even where the row would otherwise break inside it."""
    cr, size = _ctx(), 50
    line = "春夏秋冬东南西北上下左右"
    max_w = text_width(cr, line[:6], size) + 1
    assert not any("南西" in r for r in wrap(cr, line, size, max_w))    # left alone, it breaks between 南 and 西
    rows = wrap(cr, line, size, max_w, keep=["南西"])
    assert any("南西" in r for r in rows), rows
    assert all(text_width(cr, r, size) <= max_w for r in rows)


def test_highlight_words_reach_the_timeline_in_each_language(tmp_path):
    from story.narrate import narrate

    config = {"tts": {"zh": {"speed": 1.0, "voice": "x"}, "en": {"speed": 1.0, "voice": "x"},
                      "pause_s": {"sentence": 0.38, "question": 0.5, "colon": 0.3, "paragraph": 0.7}},
              "paths": {"models": str(tmp_path), "cache": str(tmp_path)}}
    shots = [{"id": 1, "act": "a", "narration": "有的人先看机会，有的人先想风险。", "scene": "walk", "params": {},
              "narration_en": "Some see the opportunity, others the risk.", "highlight": ["机会", "风险"],
              "highlight_en": ["opportunity", "risk"]},
             {"id": 2, "act": "a", "narration": "没有关键词的一句。", "narration_en": "A plain line.",
              "scene": "walk", "params": {}}]
    _, zh = narrate({"shots": shots}, config, draft=True)
    _, en = narrate({"shots": shots}, config, lang="en", draft=True)
    assert [t["highlight"] for t in zh["shots"]] == [["机会", "风险"], []]
    assert [t["highlight"] for t in en["shots"]] == [["opportunity", "risk"], []]


def test_markdown_title_and_bold_marks_are_not_narration():
    """A script written in Markdown: the `# title` line is for the reader and **bold** marks are formatting, so
    shots that leave them out still match the script."""
    from story.narrate import check_script

    script = "# 看对趋势的人很多\n\n当时流行一句话：\n\n**守币，比守寡还难。**\n\n## 小节\n\n结尾。\n"
    check_script({"shots": [{"narration": "当时流行一句话："}, {"narration": "守币，比守寡还难。结尾。"}]}, script)


def test_compare_bubbles_sit_over_the_two_heads_and_their_words_fit():
    """Each thought bubble stays on screen, above its person's head, clear of the other bubble, and the longest
    line of words fits inside it, in both formats."""
    import cairo

    from story.scenes.compare import HEAD_TOP, bubble_top, fit, layout
    from story.stage import Stage

    cr = _ctx()
    words = [["Untested?", "What breaks?", "Enough time?"], ["Great, we're finally launching!"]]
    for W, H_ in ((1920, 1080), (1080, 1920)):
        st = Stage(W, H_)
        (hx, ox), (top, bottom), width = layout(st)
        assert 0 < top < bottom < st.horizon - HEAD_TOP * st.s, (W, top, bottom)
        assert hx - width / 2 >= 0 and ox + width / 2 <= W and hx + width / 2 < ox - width / 2
        rows, size = fit(cr, st, words)
        assert size >= 40 * st.u, (W, size)                     # long lines wrap rather than shrink to nothing
        assert [" ".join(r) for r in rows] == [" ".join(w) for w in words]
        assert max(text_width(cr, s, size, cairo.FONT_WEIGHT_BOLD) for r in rows for s in r) <= width - 60 * st.u
        for r in rows:
            assert top <= bubble_top(st, r, size) < bottom - len(r) * size * 1.35
        assert rows[0] == words[0], rows                         # short lines stay whole


OBJECT_CASES = {
    "book": [{}, {"flips": 3}, {"close": True, "title": "一本很厚很厚很厚很厚很厚的书"}],
    "screen": [{}, {"off": True}, {"device": "laptop", "lines": ["重点", "摘要", "思维导图", "这一行特别特别特别特别长"]}],
    "chat": [{}, {"count": 4}, {"bubbles": ["帮我读完这本书", "好的，这是重点、摘要和一份很长很长很长很长的思维导图"]}],
    "map": [{}, {"off": True}],
    "chart": [{}, {"trend": "down", "color": "red"}, {"values": [3, 1, 4, 1, 5], "labels": ["2018 年 12 月", "2021"]}],
}


def test_object_scenes_float_above_the_hero_and_their_words_fit():
    """Books, screens, chats, maps and charts stay inside the frame and above the hero's head, and every word
    on them fits its space, in both formats."""
    import importlib

    from story.scenes import _objects
    from story.scenes.compare import HEAD_TOP
    from story.stage import Stage

    cr = _ctx()
    for W, H_ in ((1920, 1080), (1080, 1920)):
        st = Stage(W, H_)
        reach = _objects.hero_x(st) + _objects.HERO_REACH * st.s
        head = st.horizon - HEAD_TOP * st.s
        mx, my, mr = _objects.moon(st)
        for name, cases in OBJECT_CASES.items():
            mod = importlib.import_module(f"story.scenes.{name}")
            for params in cases:
                L = mod.layout(cr, st, params)
                x0, y0, x1, y1 = L["box"]
                assert 0 <= x0 < x1 <= W and 0 <= y0 < y1 < st.horizon, (name, W, params, L["box"])
                assert x0 > reach or y1 < head, (name, W, params, "touches the hero")
                nearest = (min(max(mx, x0), x1), min(max(my, y0), y1))          # the box point closest to the moon
                assert math.dist(nearest, (mx, my)) > mr * 0.5, (name, W, params, "covers the moon")
                for word, size, room in L["texts"]:
                    assert size >= 20 * st.u, (name, word, size)
                    assert text_width(_ctx(), word, size) <= room + 0.5, (name, word, size, room)


def test_object_scenes_draw_every_moment_without_errors():
    """Each object scene draws from start to end with each of its options, in both formats."""
    import importlib

    import cairo

    from story.stage import Stage

    for W, H_ in ((1920, 1080), (1080, 1920)):
        st = Stage(W, H_)
        cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H_))
        for name, cases in OBJECT_CASES.items():
            mod = importlib.import_module(f"story.scenes.{name}")
            for params in cases:
                for p in (0.0, 0.1, 0.3, 0.55, 0.7, 0.9, 1.0):
                    st.t = p * 5
                    assert mod.hero(st, p, 5.0, params)["x"] > 0
                    mod.draw(cr, st, p, 5.0, 1.0, params)


def test_chart_labels_stay_over_the_plot():
    from story.scenes import chart
    from story.stage import Stage

    cr = _ctx()
    for W, H_ in ((1920, 1080), (1080, 1920)):
        st = Stage(W, H_)
        params = {"labels": ["2018 年 12 月", "2021 年"]}
        L = chart.layout(cr, st, params)
        pts = chart.curve(params, L["plot"])
        for i, word in enumerate(L["labels"]):
            half = text_width(cr, word, L["size"]) / 2
            x = chart.label_x(cr, L, pts, i)
            assert L["plot"][0] <= x - half and x + half <= L["plot"][2] + 0.5


def test_screen_rows_never_overlap():
    """Words on a screen sit one per row; each row is taller than its words, on a phone and on a laptop."""
    from story.scenes import screen
    from story.stage import Stage

    cr = _ctx()
    for W, H_ in ((1920, 1080), (1080, 1920)):
        st = Stage(W, H_)
        for device in ("phone", "laptop"):
            L = screen.layout(cr, st, {"device": device, "lines": ["重点", "摘要", "思维导图", "第四行"]})
            assert L["size"] * 1.25 <= L["step"], (W, device, L["size"], L["step"])


def test_portrait_puts_wide_objects_overhead_and_tall_ones_beside_the_hero():
    from story.scenes import _objects
    from story.stage import Stage

    st = Stage(1080, 1920)
    wide, tall = _objects.region(st, aspect=1.5), _objects.region(st, aspect=0.5)
    assert wide[0] == st.W / 2 and tall[0] > st.W / 2


def test_portrait_shows_a_laptop_as_a_phone_so_its_words_stay_large():
    from story.scenes import screen
    from story.stage import Stage

    cr = _ctx()
    params = {"device": "laptop", "lines": ["重点", "摘要", "思维导图"]}
    land, port = Stage(1920, 1080), Stage(1080, 1920)
    assert screen.device(land, params) == "laptop" and screen.device(port, params) == "phone"
    assert screen.layout(cr, port, params)["size"] >= 56 * port.u


def test_balancing_rows_never_cuts_an_english_word():
    """Evening out the rows must not narrow them past a whole word: "understanding" stays in one piece."""
    cr = _ctx()
    q = "it can't do the understanding for you"
    for size, max_w in ((92, 1080 * 0.80), (58, 1080 * 0.76), (92, 1920 * 0.86)):
        rows = wrap(cr, q, size, max_w)
        assert " ".join(rows) == q, rows
        assert all(text_width(cr, r, size) <= max_w for r in rows), rows


def test_chinese_defaults_to_portrait_and_english_to_landscape():
    """视频号 (Chinese) is watched on phones: portrait by default; X (English) stays landscape.  --portrait still
    gives both formats, --only exactly one."""
    from types import SimpleNamespace

    from story.render import formats_for

    plain = SimpleNamespace(only=None, portrait=False)
    assert formats_for("zh", plain) == ["portrait"]
    assert formats_for("en", plain) == ["landscape"]
    both = SimpleNamespace(only=None, portrait=True)
    assert formats_for("zh", both) == formats_for("en", both) == ["landscape", "portrait"]
    assert formats_for("zh", SimpleNamespace(only="landscape", portrait=False)) == ["landscape"]


# ---------- scenery: forested mountains, lamps, benches ----------
def _forest_args():
    from story.stage import M_MID, hexc

    return dict(peaks=[(200.0, 0.55, 300.0), (420.0, 0.6, 260.0)], colors=M_MID, tree_density=1.5, tree_scale=20,
                W=480, H=270, horizon=210.0, u=0.25, speed=0.25, lift_k=0.9,
                tree_colors=[(hexc("4f4b66"), hexc("3b3851")), (hexc("48445f"), hexc("36334b"))])


def test_forest_is_the_same_on_every_render_and_changes_with_the_seed():
    from story.forest import forest_mountain_layer

    a = forest_mountain_layer(seed=3, **_forest_args())
    b = forest_mountain_layer(seed=3, **_forest_args())
    c = forest_mountain_layer(seed=4, **_forest_args())
    assert bytes(a.surface.get_data()) == bytes(b.surface.get_data())
    assert bytes(a.surface.get_data()) != bytes(c.surface.get_data())
    assert a.trees > 100


def test_trees_cover_the_peak_to_the_summit_and_line_both_ridges():
    """Trees right up to the summit (smaller there), with a row on each ridge (the saw-tooth)."""
    import random
    from story.forest import _slope_trees

    cx, py, base, half, line_y, bottom = 500.0, 100.0, 1400.0, 2000.0, 140.0, 400.0
    trees = _slope_trees(random.Random(1), cx, py, half, base, line_y, bottom, 1.5, 20.0, 3)
    assert trees and all(tr.y >= line_y for tr in trees)
    top = [tr for tr in trees if tr.y < line_y + (bottom - line_y) * 0.1]
    assert top and max(tr.h for tr in top) < 20.0 * 1.3 * 0.7    # small trees at the summit
    slope = half / (base - py)
    for side in (-1, 1):
        on_ridge = [tr for tr in trees if abs(tr.x - (cx + side * slope * (tr.y - py))) < tr.h * 0.3]
        assert len(on_ridge) > 10, side
    low = sum(tr.y > (line_y + bottom) / 2 for tr in trees)
    assert low > len(trees) - low                       # thickest at the foot


def test_scenery_is_off_unless_the_storyboard_asks(tmp_path):
    from story.narrate import narrate
    from story.stage import Stage

    assert not Stage(480, 270).scenery and not hasattr(Stage(480, 270), "forest")
    config = {"tts": {"zh": {"speed": 1.0, "voice": "x"}, "pause_s": {"sentence": 0.38, "question": 0.5,
                                                                     "colon": 0.3, "paragraph": 0.7}},
              "paths": {"models": str(tmp_path), "cache": str(tmp_path)}}
    shots = [{"id": 1, "act": "a", "narration": "路上总会有石头。", "scene": "walk", "params": {}}]
    assert narrate({"shots": shots}, config, draft=True)[1]["scenery"] is False
    assert narrate({"shots": shots, "scenery": True}, config, draft=True)[1]["scenery"] is True


def test_roadside_props_stay_out_of_shots_that_need_the_space():
    """Lamps and benches only while the hero walks; a shot can force them on or off."""
    from story.render import Film

    def shot(i, scene, **extra):
        return {"id": i, "scene": scene, "params": {}, "narration": "x", "start": i * 5.0, "end": i * 5.0 + 5,
                "subs": [], "quote": None, **extra}
    tl = {"duration": 25.0, "lang": "zh", "scenery": True,
          "shots": [shot(0, "walk"), shot(1, "book"), shot(2, "fork"), shot(3, "face_camera"),
                    shot(4, "book", roadside=True)]}
    film = Film(tl, 480, 270, 1)
    assert [film._roadside(i) for i in range(5)] == [1.0, 0.0, 0.0, 0.0, 1.0]
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 480, 270)
    for t in (0.5, 5.3, 12.0, 24.0):                    # including mid-way through a shot change
        film.draw(cairo.Context(surf), t)


def test_a_street_lamp_is_drawn_whole_or_not_at_all():
    """A lamp whose post has left the frame must not leave its head hanging in the corner (and a lamp whose
    head is still outside must not stand there as a bare post)."""
    import cairo
    import numpy as np
    from story.stage import Camera, Stage
    st = Stage(1080, 1920, scenery=True)
    wx = st.props.lamps[0]
    for post_x in (-10.0, 1080 - 20.0, 1080 - 120.0):   # post off the left edge / head, or its glow, off the right
        st.cam = Camera(travel=wx - post_x)
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1080, 1920)
        st.props.roadside(cairo.Context(surf), st, 0.0, 1.0)
        surf.flush()
        px = np.ndarray((1920, surf.get_stride() // 4, 4), np.uint8, surf.get_data())[:, :1080]
        top = int(st.horizon - 300 * st.s)
        band = px[top:int(st.horizon) + 5, :200] if post_x < 0 else px[top:int(st.horizon) + 5, 880:]
        assert band[..., 3].max() == 0, f"part of a lamp drawn with its post at x={post_x}"
