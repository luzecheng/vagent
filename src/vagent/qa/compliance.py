"""Compliance scan for high-risk wording (report only; the author's text is never changed).

Rules are deliberately specific so ordinary life / mindset scripts do not trip
them.  For finance / crypto scripts an extra Claude review may add findings,
but each one must quote text that really exists in the script.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re

from pydantic import BaseModel, Field


@dataclass
class Finding:
    level: str        # high | medium
    category: str
    quote: str
    sentence_id: int | None
    reason: str
    source: str = "rule"


RULES: list[tuple[str, str, str, str]] = [
    # (level, category, regex, reason) -- within an alternation, list longer phrases first so the quote is complete
    ("high", "保证收益", r"保证(收益|赚|回报|盈利)|包赚|稳赚不赔|只赚不赔|稳赚|稳赢|躺赚|无风险|零风险|没有风险的(投资|收益)",
     "承诺收益 / 否认风险，视频号对此审核严格"),
    ("high", "保证收益", r"\bguaranteed? (returns?|profits?|gains?)\b|\brisk[- ]free\b|\bcan'?t lose\b|\bsure thing\b",
     "promises returns or denies risk"),
    ("high", "价格预测", r"(必涨|一定(会)?涨|肯定(会)?涨|必然(上涨|暴涨)|稳涨|必跌|一定(会)?跌|肯定(会)?跌)",
     "确定性价格判断"),
    ("high", "价格预测", r"(涨|跌|冲|看)到\s*\d[\d,.]*\s*(万|千|美元|美金|刀|块|元|u|U)?|目标价|\d[\d,.]*\s*(倍|x|X)\s*(币|收益|回报)",
     "具体价格 / 倍数预测"),
    ("high", "价格预测", r"\b(price target|will (hit|reach) \$?\d|to the moon|\d+x (coin|gem|return))\b", "price prediction"),
    ("high", "买卖指令", r"(现在|马上|立刻|赶紧|赶快|今天|闭眼)(就)?(买|卖|上车|抄底|梭哈|清仓|加仓|满仓)|梭哈|all\s*in|满仓干|无脑(买|冲)",
     "明确的买卖指令"),
    ("high", "买卖指令", r"\b(buy now|sell now|ape in|go all in|load up now|back up the truck)\b", "explicit buy/sell call"),
    ("medium", "诱导话术", r"(最后一次|错过(就|再)?(没有|等)|再不(买|上车)就|跟着我(买|操作|上车)|私信(我|领取)|加群|带你(赚|翻倍)|财富密码)",
     "诱导性 / 引流话术"),
    ("medium", "诱导话术", r"\b(don'?t miss out|last chance|dm me|join my group|follow my trades)\b", "inducement / FOMO wording"),
    ("medium", "收益暗示", r"(暴富|翻\s*\d+\s*倍|财务自由只需|轻松月入|年化\s*\d+\s*%)", "夸大收益暗示"),
]


# "Should I buy now?" asks whether to buy; it is not telling anyone to buy
QUESTION_LEAD = re.compile(r"\b(should|shall|do|can|could|would) (i|we|you)\b|\bwhether\b|\bis it time to\b|"
                           r"\bwhen to\b|要不要|是不是该|是不是要|该不该|能不能|可不可以|是否", re.IGNORECASE)
CLAUSE_END = re.compile(r"[，。！？；,.!?;]")


def _asks_whether(text: str, start: int) -> bool:
    """The match sits in a question clause that is led by a 'should I / 要不要' style lead."""
    clause_start = max((m.end() for m in CLAUSE_END.finditer(text, 0, start)), default=0)
    end = CLAUSE_END.search(text, start)
    closes_with_question = end is not None and end.group(0) in "？?"
    return closes_with_question and bool(QUESTION_LEAD.search(text, clause_start, start))


def scan(sentences: list[dict]) -> list[Finding]:
    """sentences: [{"id", "text"}] in either language."""
    findings: list[Finding] = []
    for sentence in sentences:
        text = sentence["text"]
        for level, category, pattern, reason in RULES:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                if category == "买卖指令" and _asks_whether(text, match.start()):
                    continue
                findings.append(Finding(level, category, match.group(0), sentence["id"], reason))
    return findings


class ReviewItem(BaseModel):
    sentence_id: int
    quote: str = Field(description="exact substring of that sentence")
    category: str = Field(description="保证收益 / 价格预测 / 买卖指令 / 诱导话术 / 其他")
    level: str = Field(description="high or medium")
    reason: str


class Review(BaseModel):
    items: list[ReviewItem]


REVIEW_SYSTEM = """You review a Chinese finance / crypto short-video script for wording that WeChat Channels
moderation treats as high risk: promising returns or denying risk, definite price predictions or
targets, explicit buy/sell instructions, and inducement (FOMO, "follow my trades", private groups).
Opinions, long-term reasoning, risk warnings and position-sizing advice are NOT violations.
Quote the exact risky substring. Return an empty list if nothing is risky. Return JSON only."""


def llm_review(sentences: list[dict], config: dict, log=None) -> list[Finding]:
    from .. import cache as cachemod
    from ..llm.client import structured

    texts = {s["id"]: s["text"] for s in sentences}
    user = "\n".join(f"{i}. {t}" for i, t in texts.items())

    def check(review: Review):
        return [f"item quote '{item.quote}' is not an exact substring of sentence {item.sentence_id}"
                for item in review.items if item.quote not in texts.get(item.sentence_id, "")]

    store = cachemod.Cache(config["paths"]["cache"], "llm/compliance")
    digest = cachemod.key(REVIEW_SYSTEM, user, config["llm"]["model"])
    cached = store.get_json(digest)
    review = Review.model_validate(cached) if cached is not None else structured(Review, REVIEW_SYSTEM, user, config,
                                                                                 log, check)
    store.put_json(digest, review.model_dump())
    return [Finding("high" if item.level == "high" else "medium", item.category, item.quote, item.sentence_id,
                    item.reason, source="claude") for item in review.items if item.quote in texts.get(item.sentence_id, "")]


def as_dicts(findings: list[Finding]) -> list[dict]:
    return [asdict(f) for f in findings]
