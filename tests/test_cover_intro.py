"""The finished video opens on its cover (first frame = platform thumbnail) and carries the cover as file artwork."""
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image
import pytest

from vagent import config as configmod
from vagent.plan.schema import Storyboard
from vagent.plan.timing import scene_specs
from vagent.render import engine
from vagent.render.cover import render_cover
from vagent.render.theme import theme as make_theme, variant as make_variant


def _board():
    scenes = [{"id": f"s0{i}", "sentence_ids": [i], "component": "keyword",
               "params_zh": {"word": "词"}, "params_en": {"word": "w"}} for i in (1, 2, 3)]
    scenes[0]["component"] = "hook"
    scenes[0]["params_zh"] = scenes[0]["params_en"] = {"line": "x"}
    return Storyboard.model_validate({"content_type": "mindset", "disclaimer": {"on": False, "reason": ""},
                                      "hook_sentence_id": 1, "scenes": scenes})


def _timeline(lead):
    sentences, t = [], lead
    for i in (1, 2, 3):
        sentences.append({"id": i, "start": t + 0.05, "end": t + 1.5, "clip_start": t, "clip_end": t + 1.6})
        t += 2.0
    return {"sentences": sentences, "duration": t}


def test_first_scene_starts_after_the_cover():
    specs = scene_specs(_board(), _timeline(0.75), "en", intro=0.5)
    assert specs[0].start == 0.5
    assert specs[0].end == specs[1].start
    assert scene_specs(_board(), _timeline(0.25), "en")[0].start == 0.0   # no cover: unchanged


def test_video_cover_text_stays_in_the_variant_safe_area(tmp_path):
    config = configmod.load()
    v = make_variant("zh_shipinhao", 1080, 1920)
    records = render_cover("把习惯做小，从今天开始", "小到状态再差也能做到", make_theme(config, "zh"), (1080, 1920),
                           tmp_path / "c.png", area=v.content)
    assert records and all(v.content.contains(r.box, 1.0) for r in records)


def _probe(path):
    return json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
                                     capture_output=True, text=True, check=True).stdout)["streams"]


def test_video_opens_on_the_cover_and_embeds_it_as_artwork(tmp_path):
    v = make_variant("en_x", 1080, 1920)
    Image.new("RGB", (1080, 1920), (200, 30, 30)).save(tmp_path / "cover.png")       # red cover
    scene = tmp_path / "scene.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=blue:s=1080x1920:r=30:d=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(scene)], check=True)
    cover_clip = engine.still_clip(tmp_path / "cover.png", 0.5, 30, tmp_path / "cover.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-t", "2.5", str(tmp_path / "a.wav")], check=True)
    out = tmp_path / "out.mp4"
    engine.composite([{"path": str(cover_clip)}, {"path": str(scene)}], [], tmp_path / "a.wav", out, v, 30,
                     tmp_path / "work", duration=2.5)
    Image.new("RGB", (1080, 1440), (30, 200, 30)).save(tmp_path / "art.png")
    engine.embed_artwork(out, tmp_path / "art.png")

    def frame(t):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(out), "-frames:v", "1", "-f",
                              "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
        return np.frombuffer(raw, np.uint8).reshape(1920, 1080, 3)[960, 540]

    assert frame(0.0)[0] > 150 and frame(0.0)[2] < 80          # first frame is the (red) cover
    assert frame(1.5)[2] > 150                                  # then the video
    streams = _probe(out)
    assert streams[0]["codec_type"] == "video" and streams[0]["codec_name"] == "h264"
    art = [s for s in streams if s.get("disposition", {}).get("attached_pic")]
    assert len(art) == 1 and art[0]["width"] == 1080 and art[0]["height"] == 1440
    assert sum(1 for s in streams if s["codec_type"] == "audio") == 1


def test_composite_accepts_relative_clip_paths(tmp_path, monkeypatch):
    """`vagent run --out output/x` gives relative paths; ffmpeg's concat list resolves them against itself."""
    monkeypatch.chdir(tmp_path)
    v = make_variant("en_x", 1080, 1920)
    Path("it's here").mkdir()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=blue:s=1080x1920:r=30:d=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "it's here/a.mp4"], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-t", "1", "a.wav"], check=True)
    engine.composite([{"path": "it's here/a.mp4"}], [], Path("a.wav"), Path("out.mp4"), v, 30, Path("work/compose"),
                     duration=1.0)
    assert Path("out.mp4").stat().st_size > 0
