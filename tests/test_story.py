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
