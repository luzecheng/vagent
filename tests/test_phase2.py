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


def test_every_icon_parses_and_draws_on():
    from vagent.render import icons
    from vagent.render.canvas import Canvas

    assert len(icons.names()) > 100
    for name in icons.names():
        assert icons.strokes(name), name
    c = Canvas(200, 200, (0, 0, 0))
    icons.draw(c, "home", 100, 100, 120, (255, 255, 255), progress=0.5)
    assert c.finish().getbbox() is not None


def test_svg_arc_and_relative_commands():
    from vagent.render.icons import parse_path

    (line,) = parse_path("M2 12a10 10 0 1 0 20 0a10 10 0 1 0 -20 0")  # a full circle of radius 10
    assert all(abs(((x - 12) ** 2 + (y - 12) ** 2) ** 0.5 - 10) < 1e-6 for x, y in line)
    (line,) = parse_path("M5 12l-2 0l9 -9l9 9h-2v7z")
    assert line[:4] == [(5, 12), (3, 12), (12, 3), (21, 12)] and line[-1] == (5, 12)


def test_diagram_components_are_registered_with_samples_and_purposes():
    from vagent.plan.planner import PURPOSE

    for name in ("balance", "cycle", "dialogue"):
        assert name in REGISTRY and name in PURPOSE
        for lang in ("zh", "en"):
            REGISTRY[name][1].model_validate(SAMPLES[lang][name])
    assert REGISTRY["checklist"][1].model_validate({"items": ["a", "b"], "mode": "ticks"}).mode == "ticks"


@pytest.mark.parametrize("name", ["balance", "cycle", "dialogue"])
def test_diagram_components_animate(name):
    th, v = theme(CONFIG, "zh"), variant("zh_shipinhao")
    scene = engine.SceneSpec(name, name, SAMPLES["zh"][name], 0.0, 7.0, [0.3, 1.3, 2.3, 3.3])
    early, _ = engine.render_frame(scene, 0.5, th, v)
    late, records = engine.render_frame(scene, 6.0, th, v)
    assert early.tobytes() != late.tobytes()
    assert records and outside(records, v.content) == []


def test_demo_reel_names_every_component():
    from vagent.render.demo import NAMES_ZH

    assert set(NAMES_ZH) == set(REGISTRY)


@pytest.mark.parametrize("lang,vname", [("zh", "zh_shipinhao"), ("en", "en_x")])
@pytest.mark.parametrize("name", list(REGISTRY))
def test_text_stays_in_content_area_with_the_camera_push(lang, vname, name):
    # the push enlarges the frame about the content centre; text laid out flush with the content edge
    # used to end up outside it (a 4-item checklist with a title, short_vs_long labels)
    from vagent.render import motion

    th, v = theme(CONFIG, lang), variant(vname)
    params = dict(SAMPLES[lang][name])
    if name == "checklist":
        params["items"] = (params["items"] * 2)[:5]
    scene = engine.SceneSpec(name, name, params, 0.0, 7.0, [0.3, 1.3, 2.3, 3.3, 4.3])
    engine.fit_scene(scene, th, v)
    _, records = engine.render_frame(scene, 7.0 - motion.LEAVE - 0.05, th, v)
    assert outside(records, v.content) == []
