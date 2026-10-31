"""YouTube upload: what goes up, and never twice."""
import json

import pytest

from vagent.publish import youtube

NOTES = """# 发布文案

## X（English）

Made a mistake? #Principles

## YouTube（English）
Title: Mistakes Aren't the Problem
Tags: Principles, Ray Dalio, self improvement
Description:
A trader forgot to place a client's trade.
Dalio didn't fire him.
"""


class _Request:
    def __init__(self, result):
        self.result = result

    def next_chunk(self):
        return None, self.result

    def execute(self):
        return self.result


class FakeYouTube:
    def __init__(self):
        self.inserted, self.thumbs = [], []

    def videos(self):
        return self

    def thumbnails(self):
        return self

    def insert(self, part, body, media_body):
        self.inserted.append((body, media_body._filename))
        return _Request({"id": "abc123", "status": {"privacyStatus": body["status"]["privacyStatus"]}})

    def set(self, videoId, media_body):
        self.thumbs.append((videoId, media_body._filename))
        return _Request({})


def _episode(tmp_path, notes=NOTES):
    (tmp_path / "story_en_landscape.mp4").write_bytes(b"\0" * 16)
    (tmp_path / "cover_en_landscape.png").write_bytes(b"\0" * 16)
    (tmp_path / "publish_notes.md").write_text(notes, encoding="utf-8")
    return tmp_path


def test_youtube_section_is_read_not_the_x_post():
    post = youtube.read_post(NOTES)
    assert post.title == "Mistakes Aren't the Problem"
    assert post.tags == ["Principles", "Ray Dalio", "self improvement"]
    assert post.description == "A trader forgot to place a client's trade.\nDalio didn't fire him."


def test_uploads_english_video_and_cover_privately_by_default(tmp_path):
    yt = FakeYouTube()
    out = youtube.upload(_episode(tmp_path), yt)
    (body, video), = yt.inserted
    assert video.endswith("story_en_landscape.mp4") and body["status"]["privacyStatus"] == "private"
    assert body["snippet"]["title"] == "Mistakes Aren't the Problem"
    assert yt.thumbs == [("abc123", str(tmp_path / "cover_en_landscape.png"))]
    assert out["url"] == "https://youtu.be/abc123" and out["thumbnail"] == "set"
    assert json.loads((tmp_path / "youtube.json").read_text())["id"] == "abc123"


def test_an_uploaded_episode_is_never_uploaded_again(tmp_path):
    yt = FakeYouTube()
    youtube.upload(_episode(tmp_path), yt)
    with pytest.raises(youtube.PublishError, match="already uploaded"):
        youtube.upload(tmp_path, yt)
    assert len(yt.inserted) == 1


def test_missing_or_invalid_text_stops_before_uploading(tmp_path):
    yt = FakeYouTube()
    with pytest.raises(youtube.PublishError, match="no '## YouTube' section"):
        youtube.upload(_episode(tmp_path, NOTES.split("## YouTube")[0]), yt)
    with pytest.raises(youtube.PublishError, match="title"):
        youtube.read_post(NOTES.replace("Mistakes Aren't the Problem", "x" * 101))
    assert yt.inserted == []
