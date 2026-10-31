"""Whisper alignment for engines without timings (CosyVoice): per-character times for subtitles and shot cuts."""
import numpy as np
import soundfile as sf

from vagent import cache as cachemod
from vagent.audio import narration
from vagent.subtitles import align as alignmod
from vagent.tts.base import SR, Speech, Unit

TEXT = "你不一定会被说服，但一定会多看到一点东西。"
HEARD = list("你不一定会被说服但一定会多看到一点东西")


def _voice(seconds=4.0):
    return np.full(int(seconds * SR), 0.2, np.float32)


def _evenly(chars, start, end):
    step = (end - start) / len(chars)
    return [(c, start + i * step, start + (i + 1) * step) for i, c in enumerate(chars)]


def test_prompt_hallucination_falls_back_to_unprompted_transcript(monkeypatch):
    """Seen on ep 09: with the sentence as initial prompt Whisper invented "请点赞、订阅、打赏" and only 5% of the
    characters matched, so the first half of the sentence was squeezed into 0.3 s and its subtitle flashed by."""
    def recognised(audio, text, lang, prompt):
        return _evenly("请点赞订阅打赏", 0.0, 4.0) if prompt else _evenly(HEARD, 0.0, 4.0)

    monkeypatch.setattr(alignmod, "_recognised_units", recognised)
    units, matched = alignmod.align(_voice(), TEXT, "zh")
    assert matched == 1.0
    assert units[8].text == "但" and abs(units[8].start - 8 * 4.0 / 19) < 0.01


def test_prompt_used_when_it_matches_more(monkeypatch):
    """The prompt still helps on some clips (homophones); the better-matching transcript wins."""
    partial = ["你", "不", "一", "定", "回", "背", "说", "服"] + HEARD[8:]
    monkeypatch.setattr(alignmod, "_recognised_units",
                        lambda audio, text, lang, prompt: _evenly(HEARD if prompt else partial, 0.0, 4.0))
    _, matched = alignmod.align(_voice(), TEXT, "zh")
    assert matched == 1.0


def test_cached_sentence_from_older_alignment_is_realigned_without_resynthesis(tmp_path, monkeypatch):
    class Provider:
        def cache_identity(self):
            return "fake"

        def synth(self, text, lang, voice, speed):
            raise AssertionError("the cached audio must be reused")

    store = cachemod.Cache(str(tmp_path), "tts/zh")
    digest = cachemod.key("fake", "zh", "v", 1.0, TEXT)
    sf.write(store.path(digest, ".wav"), _voice(), SR)
    squeezed = [{"text": c, "start": 0.04 * i, "end": 0.04 * (i + 1)} for i, c in enumerate(HEARD)]
    store.put_json(digest, {"units": squeezed, "exact": False, "engine": "fake",
                            "notes": ["Whisper-aligned (5% of units matched)"]})
    good = [Unit(c, s, e) for c, s, e in _evenly(HEARD, 0.0, 4.0)]
    monkeypatch.setattr(alignmod, "align", lambda audio, text, lang: (good, 1.0))

    speech = narration._synth_cached(Provider(), TEXT, "zh", "v", 1.0, store)
    assert speech.units == good
    again = narration._synth_cached(Provider(), TEXT, "zh", "v", 1.0, store)   # rewritten: no second alignment
    assert again.units == good and store.get_json(digest)["align_rev"] == alignmod.ALIGN_REV


def test_exact_engine_timings_are_never_realigned(tmp_path, monkeypatch):
    class Provider:
        def cache_identity(self):
            return "fake"

        def synth(self, text, lang, voice, speed):
            return Speech(_voice(1.0), [Unit("a", 0.1, 0.5)], True, "fake", [])

    store = cachemod.Cache(str(tmp_path), "tts/zh")
    narration._synth_cached(Provider(), "a", "zh", "v", 1.0, store)
    monkeypatch.setattr(alignmod, "align", lambda *a: (_ for _ in ()).throw(AssertionError("not for exact engines")))
    assert narration._synth_cached(Provider(), "a", "zh", "v", 1.0, store).units == [Unit("a", 0.1, 0.5)]


def test_a_pause_before_a_word_is_not_counted_as_that_word(monkeypatch):
    """Whisper tends to start a word at the end of the word before it, so a pause between them is given to the
    second word.  Seen on ep 11: "先说第一个，（0.45 s pause）自我意识障碍" — 自 started before the pause and the
    subtitle "先说第一个" was on screen for only 0.43 s."""
    audio = np.zeros(int(1.6 * SR), np.float32)
    t = np.arange(len(audio)) / SR
    voiced = (t < 0.6) | (t >= 1.1)
    audio[voiced] = 0.2 * np.sin(2 * np.pi * 220 * t[voiced])
    heard = [("一", 0.0, 0.3), ("二", 0.3, 0.55), ("三", 0.55, 1.3), ("四", 1.3, 1.6)]
    monkeypatch.setattr(alignmod, "_recognised_units", lambda audio, text, lang, prompt: heard)
    units, _ = alignmod.align(audio, "一二三四", "zh")
    assert abs(units[2].start - 1.1) < 0.05, units
    assert units[1].start == 0.3                       # words without a pause inside keep their time
