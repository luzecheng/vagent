"""publish_notes.md: WeChat Channels title/description/topics, X post + hashtags, cover lines.

Drafted by Claude, validated here (lengths by each platform's counting rule).
The disclaimer is appended by code when required, never left to the model.
Nothing is ever posted.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .. import cache as cachemod
from ..llm.client import structured
from ..script.text import zh_punct

URL = re.compile(r"https?://\S+")


def x_length(text: str) -> int:
    """X's weighted length: CJK and most non-Latin characters count 2, URLs count 23."""
    total = 23 * len(URL.findall(text))
    for ch in URL.sub("", text):
        total += 1 if ord(ch) <= 0x10FF or 0x2000 <= ord(ch) <= 0x200D or 0x2010 <= ord(ch) <= 0x201F \
            or 0x2032 <= ord(ch) <= 0x2037 else 2
    return total


def title_length(text: str) -> int:
    return len(re.sub(r"\s", "", text))


class Notes(BaseModel):
    shipinhao_title: str = Field(description="WeChat Channels title, Chinese, <= 16 characters, no hashtags")
    shipinhao_description: str = Field(description="2-4 short Chinese sentences, <= 200 characters")
    shipinhao_topics: list[str] = Field(min_length=3, max_length=5, description="topics without '#'")
    x_post: str = Field(description="English post body for X, punchy, no hashtags inside")
    x_hashtags: list[str] = Field(min_length=1, max_length=3, description="hashtags without '#'")
    cover_title_zh: str = Field(description="Chinese cover headline, <= 14 characters")
    cover_sub_zh: str = Field("", description="optional Chinese cover subline, <= 18 characters")
    cover_title_en: str = Field(description="English cover headline, <= 48 characters")
    cover_sub_en: str = Field("", description="optional English cover subline, <= 60 characters")


SYSTEM = """You write publishing copy for one short video, posted by its author (never by you).
WeChat Channels (Chinese): a title of at most 16 characters that makes people stop scrolling without
clickbait, a 2-4 sentence description, 3-5 topics. X (English): a post in the voice of the X
crypto / investing / mindset community: concise, punchy, line breaks allowed, no emojis spam,
1-3 hashtags returned separately. Covers: a short headline (and optional subline) per language.
Keep the author's viewpoint; add no facts, numbers, promises of returns, price targets or buy/sell
instructions. Return JSON only."""


def _full_post(notes: Notes, disclaimer_en: str | None) -> str:
    tags = " ".join("#" + t.lstrip("#").replace(" ", "") for t in notes.x_hashtags)
    body = notes.x_post.strip()
    if disclaimer_en:
        body += "\n\n" + disclaimer_en
    return body + "\n\n" + tags


def draft(zh_text: str, en_text: str, disclaimer: dict, brand: dict, config: dict, log=None) -> tuple[Notes, str]:
    disc = brand.get("disclaimer", {})
    disclaimer_en = disc.get("en") if disclaimer["on"] else None
    budget = 280 - (x_length("\n\n" + disclaimer_en) if disclaimer_en else 0)

    def check(notes: Notes):
        problems = []
        if title_length(notes.shipinhao_title) > 16:
            problems.append(f"shipinhao_title has {title_length(notes.shipinhao_title)} characters; max 16")
        if "#" in notes.shipinhao_title:
            problems.append("shipinhao_title must not contain hashtags")
        if title_length(notes.cover_title_zh) > 14:
            problems.append("cover_title_zh is longer than 14 characters")
        if len(notes.shipinhao_description) > 200:
            problems.append("shipinhao_description is longer than 200 characters")
        weighted = x_length(_full_post(notes, None))
        if weighted > budget:
            problems.append(f"x_post plus hashtags is {weighted} weighted characters; must be <= {budget}")
        if re.search(r"[一-鿿]", notes.x_post + " ".join(notes.x_hashtags)):
            problems.append("the X post must be English only")
        return problems

    user = f"Chinese script:\n{zh_text}\n\nEnglish script:\n{en_text}"
    store = cachemod.Cache(config["paths"]["cache"], "llm/publish")
    digest = cachemod.key(SYSTEM, user, budget, config["llm"]["model"], 1)
    cached = store.get_json(digest)
    if cached is not None and not check(Notes.model_validate(cached)):
        notes = Notes.model_validate(cached)
    else:
        notes = structured(Notes, SYSTEM, user, config, log, check)
        store.put_json(digest, notes.model_dump())
    for field in ("shipinhao_title", "shipinhao_description", "cover_title_zh", "cover_sub_zh"):
        setattr(notes, field, zh_punct(getattr(notes, field)))
    notes.shipinhao_topics = [zh_punct(t) for t in notes.shipinhao_topics]
    description = notes.shipinhao_description.strip()
    if disclaimer["on"]:
        description += "\n\n" + disc.get("zh", "")
    topics = " ".join("#" + t.lstrip("#") for t in notes.shipinhao_topics)
    post = _full_post(notes, disclaimer_en)
    markdown = "\n".join([
        "# 发布文案（只生成，不会自动发布）", "",
        "## 视频号", "",
        f"**标题**（{title_length(notes.shipinhao_title)}/16 字）：{notes.shipinhao_title}", "",
        "**简介**：", "", description, "",
        f"**话题**：{topics}", "",
        "## X", "",
        f"**推文**（{x_length(post)}/280，按 X 规则计数）：", "", "```", post, "```", "",
        "上传视频文件：`en_x_9x16.mp4`", "",
    ])
    return notes, markdown
