import pytest

from vagent import config as configmod
from vagent.qa.layout import missing_glyphs, outside
from vagent.render import engine
from vagent.render.canvas import Canvas
from vagent.render.components import REGISTRY, Ctx, draw
from vagent.render.gallery import SAMPLES
from vagent.render.theme import theme, variant

CONFIG = configmod.load()
LONG = {"zh": "这是一段故意写得非常非常长的标题文字，用来测试组件在文字超长时是否会自动缩小字号而不是溢出画面边界，"
              "同时还要保证换行不会把词语从中间断开",
        "en": "This is a deliberately very long headline written to check that components shrink the font "
              "instead of letting text run past the edge of the frame, while wrapping only between words"}


@pytest.mark.parametrize("lang,vname", [("zh", "zh_shipinhao"), ("en", "en_x")])
@pytest.mark.parametrize("name", list(REGISTRY))
def test_components_stay_in_content_area_with_full_glyphs(lang, vname, name):
    th, v = theme(CONFIG, lang), variant(vname)
    c = Canvas(v.width, v.height, th.background)
    draw(c, name, 6.0, SAMPLES[lang][name], Ctx(th, v, 7.0, [0.3, 1.3, 2.3, 3.3]))
    assert c.records, "component drew no text"
    assert outside(c.records, v.content) == []
    for record in c.records:
        assert missing_glyphs(record.text, record.font) == []


@pytest.mark.parametrize("lang", ["zh", "en"])
@pytest.mark.parametrize("name", ["hook", "punchline", "quote", "keyword"])
def test_overlong_text_shrinks_instead_of_overflowing(lang, name):
    th, v = theme(CONFIG, lang), variant("zh_shipinhao")
    params = dict(SAMPLES[lang][name])
    params["word" if name == "keyword" else "text"] = LONG[lang]
    if name == "punchline":
        params["highlight"] = ""
    scene = engine.SceneSpec("long", name, params, 0.0, 7.0)
    assert not any("still overflowing" in note for note in engine.fit_scene(scene, th, v))
    _, records = engine.render_frame(scene, 6.0, th, v)
    assert outside(records, v.content) == []


def test_shipinhao_safe_area_avoids_right_buttons_and_bottom():
    v = variant("zh_shipinhao")
    assert v.safe.right <= 0.86 * v.width + 1
    assert v.safe.bottom <= 0.80 * v.height + 1
    assert v.safe.y >= 0.15 * v.height - 1
    x = variant("en_x")
    assert x.safe.bottom <= 0.85 * x.height + 1 and x.safe.y >= 0.15 * x.height - 1


def test_subtitle_images_fit_inside_band(tmp_path):
    for lang, vname, line in (("zh", "zh_shipinhao", "明天我还能不能继续做下去的"),
                              ("en", "en_x", "Can I really keep this going every day")):
        th, v = theme(CONFIG, lang), variant(vname)
        subs = engine.subtitle_images([{"lines": [line, line], "start": 0, "end": 1}], th, v, tmp_path / lang)
        assert v.subtitles.contains(subs[0].box)
        assert v.safe.contains(subs[0].box)


def test_missing_glyph_detection_flags_unsupported_characters():
    th = theme(CONFIG, "en")
    assert missing_glyphs("Hello", th.font("bold")) == []
    assert missing_glyphs("你好", th.font("bold")) == ["你", "好"]  # Inter has no CJK


def test_scene_cache_key_changes_with_drawing_code(monkeypatch):
    th, v = theme(CONFIG, "zh"), variant("zh_shipinhao")
    scene = engine.SceneSpec("s", "keyword", {"word": "底线"}, 0.0, 3.0)
    before = engine._scene_key(scene, th, v, 30)
    monkeypatch.setattr(engine, "CODE", "different-code")
    assert engine._scene_key(scene, th, v, 30) != before
