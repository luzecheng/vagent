import numpy as np
import soundfile as sf

from vagent.audio.mix import mix
from vagent.audio.music import compose
from vagent.publish.notes import Notes, _full_post, title_length, x_length
from vagent.script.text import zh_punct


def test_x_length_counts_cjk_double_and_urls_as_23():
    assert x_length("hello") == 5
    assert x_length("你好") == 4
    assert x_length("see https://example.com/a/very/long/path") == 4 + 23


def test_title_length_ignores_spaces():
    assert title_length("先把习惯 做小一点") == 8


def test_disclaimer_is_appended_by_code():
    notes = Notes(shipinhao_title="t", shipinhao_description="d", shipinhao_topics=["a", "b", "c"],
                  x_post="Stack sats, stay humble.", x_hashtags=["Bitcoin"], cover_title_zh="标题", cover_title_en="T")
    post = _full_post(notes, "Not financial advice.")
    assert post == "Stack sats, stay humble.\n\nNot financial advice.\n\n#Bitcoin"
    assert "Not financial advice" not in _full_post(notes, None)


def test_zh_punctuation_normalised_only_after_chinese():
    assert zh_punct("亲手选择,自己负责?") == "亲手选择，自己负责？"
    assert zh_punct("BTC, ETH?") == "BTC, ETH?"
    assert zh_punct({"a": ["你好,世界"]}) == {"a": ["你好，世界"]}


def test_music_varies_with_seed_and_is_stereo():
    a, b = compose(12.0, 1), compose(12.0, 2)
    assert a.shape == (12 * 48000, 2)
    assert not np.allclose(a, b)
    assert np.max(np.abs(a)) <= 1.0


def test_mix_hits_target_loudness_with_music_below_voice(tmp_path):
    sr = 24000
    t = np.arange(int(8 * sr)) / sr
    # speech-like test signal: 220 Hz bursts with pauses
    voice = (0.2 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 0.7 * t) > 0)).astype(np.float32)
    path = tmp_path / "voice.wav"
    sf.write(path, voice, sr)
    out, stats = mix(path, 10.0, 3, tmp_path / "mix")
    assert abs(stats["final_lufs"] - (-16.0)) <= 0.5
    assert stats["peak_dbtp"] <= -1.0
    assert stats["music_lufs"] <= stats["final_lufs"] - 10
    audio, rate = sf.read(out)
    assert rate == 48000 and audio.shape[1] == 2 and abs(len(audio) / rate - 10.0) < 0.05


def test_mix_without_music_is_voice_only_at_target_loudness(tmp_path):
    sr = 24000
    t = np.arange(int(8 * sr)) / sr
    voice = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    voice[3 * sr:5 * sr] = 0                       # a pause: with music off it must stay silent
    path = tmp_path / "voice.wav"
    sf.write(path, voice, sr)
    out, stats = mix(path, 10.0, 3, tmp_path / "mix", music=False)
    assert abs(stats["final_lufs"] - (-16.0)) <= 0.5
    assert stats["music_lufs"] is None
    audio, rate = sf.read(out)
    pause = audio[int(3.3 * rate):int(4.7 * rate)]
    tail = audio[int(8.5 * rate):]                 # after the voice ends (the end card)
    assert np.max(np.abs(pause)) < 1e-3 and np.max(np.abs(tail)) < 1e-3
