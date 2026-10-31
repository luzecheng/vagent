"""Upload a finished story episode's English video to the user's own YouTube channel.

Only run on the user's explicit word ("发"), never as part of rendering. The video, its cover and the text come
from the episode folder: `story_en_landscape.mp4`, `cover_en_landscape.png` and the "## YouTube" section of
`publish_notes.md`:

    ## YouTube（English）
    Title: Mistakes Aren't the Problem
    Tags: Principles, Ray Dalio, self improvement
    Description:
    any number of lines, up to the next "## " heading

OAuth: the client file from Google Cloud (a "desktop app" client) is `config/youtube_client_secret.json`; the
first upload opens a browser for the user to allow access and stores the token in `config/youtube_token.json`.
Both are personal and git-ignored.  The result is recorded in `<folder>/youtube.json`, and a folder that has one
is not uploaded again (no accidental duplicates).

Uploads from an API project that has not passed YouTube's compliance audit are locked to private.
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import json
from pathlib import Path
import re

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
PRIVACY = ("private", "unlisted", "public")
EDUCATION = "27"
TITLE_MAX, DESCRIPTION_MAX, TAGS_MAX = 100, 5000, 500


class PublishError(Exception):
    pass


@dataclass
class Post:
    title: str
    description: str
    tags: list[str]


def read_post(notes: str) -> Post:
    """The YouTube section of publish_notes.md, checked against YouTube's limits."""
    m = re.search(r"^## YouTube[^\n]*\n(.*?)(?=^## |\Z)", notes, re.M | re.S)
    if not m:
        raise PublishError("publish_notes.md has no '## YouTube' section")
    body = m.group(1)
    title = re.search(r"^Title:\s*(.+)$", body, re.M)
    tags = re.search(r"^Tags:\s*(.+)$", body, re.M)
    desc = re.search(r"^Description:\s*\n(.*)", body, re.M | re.S)
    if not (title and desc):
        raise PublishError("the YouTube section needs 'Title:' and 'Description:'")
    post = Post(title.group(1).strip(), desc.group(1).strip(),
                [t.strip() for t in tags.group(1).split(",") if t.strip()] if tags else [])
    if not post.title or len(post.title) > TITLE_MAX or "<" in post.title or ">" in post.title:
        raise PublishError(f"title must be 1–{TITLE_MAX} characters without < or >: {post.title!r}")
    if not post.description or len(post.description.encode()) > DESCRIPTION_MAX or "<" in post.description \
            or ">" in post.description:
        raise PublishError(f"description must be 1–{DESCRIPTION_MAX} bytes without < or >")
    if sum(len(t) + 1 for t in post.tags) > TAGS_MAX:
        raise PublishError(f"tags add up to more than {TAGS_MAX} characters")
    return post


def credentials(config_dir: Path):
    """Stored OAuth token, refreshed when expired; the first time, the user allows access in the browser."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    secret, token = config_dir / "youtube_client_secret.json", config_dir / "youtube_token.json"
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not (creds and creds.valid):
        if not secret.exists():
            raise PublishError(f"missing {secret}: download the desktop-app OAuth client JSON from Google Cloud")
        creds = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES).run_local_server(port=0)
    token.write_text(creds.to_json(), encoding="utf-8")
    token.chmod(0o600)
    return creds


def service(config_dir: Path):
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=credentials(config_dir), cache_discovery=False)


def upload(folder: Path, youtube, privacy: str = "private") -> dict:
    """Upload the episode's English video and cover; returns (and records) what was published."""
    from googleapiclient.http import MediaFileUpload

    if privacy not in PRIVACY:
        raise PublishError(f"privacy must be one of {', '.join(PRIVACY)}")
    record = folder / "youtube.json"
    if record.exists():
        raise PublishError(f"already uploaded: {json.loads(record.read_text(encoding='utf-8'))['url']}")
    video, cover = folder / "story_en_landscape.mp4", folder / "cover_en_landscape.png"
    if not video.exists():
        raise PublishError(f"missing {video}")
    post = read_post((folder / "publish_notes.md").read_text(encoding="utf-8"))
    body = {"snippet": {"title": post.title, "description": post.description, "tags": post.tags,
                        "categoryId": EDUCATION, "defaultLanguage": "en", "defaultAudioLanguage": "en"},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    request = youtube.videos().insert(part="snippet,status", body=body,
                                      media_body=MediaFileUpload(str(video), mimetype="video/mp4", resumable=True))
    response = None
    while response is None:
        _, response = request.next_chunk()
    out = {"id": response["id"], "url": f"https://youtu.be/{response['id']}", "title": post.title,
           "privacy": response.get("status", {}).get("privacyStatus", privacy),
           "uploadedAt": dt.datetime.now().isoformat(timespec="seconds"), "thumbnail": None}
    record.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if cover.exists():                      # needs a phone-verified channel; the video is up either way
        from googleapiclient.errors import HttpError

        try:
            youtube.thumbnails().set(videoId=out["id"], media_body=MediaFileUpload(str(cover), mimetype="image/png")
                                     ).execute()
            out["thumbnail"] = "set"
        except HttpError as exc:
            out["thumbnail"] = f"not set: {exc.reason}"
        record.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
