"""Chinese polish (light, listed) and English adaptation, aligned by sentence id."""
from __future__ import annotations

from difflib import SequenceMatcher

from pydantic import BaseModel, Field

from .. import cache as cachemod
from ..llm.client import structured
from .parse import Script, Sentence
from .text import zh_punct

PUNCT = set("，。！？；：、,.!?;:…—“”‘’\"' ")


def _words(text: str) -> str:
    return "".join(ch for ch in text if ch not in PUNCT)

MAX_ZH_CHANGE = 0.25  # a polished sentence must stay >= 75% similar to the original


class ZhLine(BaseModel):
    id: int
    text: str = Field(description="Sentence for voice-over. Identical to the original unless a light fix helps speech.")
    change_reason: str = Field("", description="Empty if unchanged; otherwise why the wording was adjusted.")


class EnLine(BaseModel):
    id: int
    text: str = Field(description="English line covering the same idea as Chinese sentence `id`. May be empty "
                                  "only when its meaning was folded into a neighbouring line.")


class Localized(BaseModel):
    zh: list[ZhLine]
    en: list[EnLine]


SYSTEM = """You prepare a short-video voice-over script in two languages.

Chinese (zh): keep the author's wording and viewpoint. Only make light edits that help it sound natural
when spoken (e.g. a missing connective, an awkward repetition). Never change the meaning, never add claims,
never soften or strengthen the opinion. Most sentences should be returned unchanged.

English (en): do NOT translate literally. Rewrite each line the way a native speaker in the X (Twitter)
crypto / investing / mindset community would say it: concise, punchy, rhythmic, plain words, no clichés,
no hashtags, no emojis. Keep the same idea, order and stance; keep every number exactly as given and do
not add numbers, facts, or promises that are not in the Chinese. One English line per Chinese sentence id.
"""


def localize(script: Script, config: dict, log=None) -> tuple[Script, Script, list[dict]]:
    numbered = "\n".join(f"{s.id}. {s.text}" for s in script.sentences)
    ids = [s.id for s in script.sentences]

    def check(result: Localized):
        problems = []
        if [z.id for z in result.zh] != ids:
            problems.append(f"zh must contain exactly ids {ids} in order")
        if [e.id for e in result.en] != ids:
            problems.append(f"en must contain exactly ids {ids} in order")
        originals = {s.id: s.text for s in script.sentences}
        for z in result.zh:
            if z.id in originals and SequenceMatcher(None, originals[z.id], z.text).ratio() < 1 - MAX_ZH_CHANGE:
                problems.append(f"zh id {z.id} changed too much; keep the original wording")
        if sum(1 for e in result.en if not e.text.strip()) > len(ids) // 4:
            problems.append("too many empty English lines")
        return problems

    user = f"Chinese script, one sentence per id:\n{numbered}"
    store = cachemod.Cache(config["paths"]["cache"], "llm/localize")
    digest = cachemod.key(SYSTEM, user, config["llm"]["model"], 1)
    cached = store.get_json(digest)
    if cached is not None:
        result = Localized.model_validate(cached)
        if log:
            log.event("llm", "Localized from cache")
    else:
        result = structured(Localized, SYSTEM, user, config, log, check)
        store.put_json(digest, result.model_dump())
    zh_sentences, en_sentences, changes = [], [], []
    for original, z, e in zip(script.sentences, result.zh, result.en):
        # punctuation-only differences are not edits: keep the author's text exactly
        text = original.text if _words(z.text) == _words(original.text) else zh_punct(z.text)
        zh_sentences.append(Sentence(original.id, text, original.paragraph, original.ends_paragraph, original.kind))
        if text != original.text:
            changes.append({"id": original.id, "before": original.text, "after": text, "reason": z.change_reason})
        if e.text.strip():
            kind = "question" if e.text.rstrip().endswith("?") else "statement"
            en_sentences.append(Sentence(original.id, e.text.strip(), original.paragraph, original.ends_paragraph, kind))
    return Script(script.raw, zh_sentences), Script(script.raw, en_sentences), changes
