"""Content type and disclaimer decision.

Deterministic keyword rule + the planner's content_type; either can turn the
disclaimer on (finance/crypto/investing), `--disclaimer on|off` overrides both.
The reasons are kept for report.md.
"""
from __future__ import annotations

import re

FINANCE_TERMS = [
    "投资", "理财", "股票", "股市", "基金", "债券", "收益率", "回报率", "年化", "复利", "仓位", "加仓", "减仓", "抄底", "止损",
    "牛市", "熊市", "比特币", "以太坊", "加密", "币圈", "代币", "山寨币", "交易所", "合约", "杠杆", "定投", "资产配置", "估值",
    "市盈率", "通胀", "利率", "美联储", "现金流", "财务自由", "存钱", "储蓄", "负债", "炒股", "持币", "囤币",
    "btc", "eth", "crypto", "bitcoin", "etf", "defi", "nft", "stock", "invest", "portfolio",
]
FINANCE_TYPES = {"investing", "crypto", "personal_finance"}


def finance_hits(text: str) -> list[str]:
    lowered = text.lower()
    hits = []
    for term in FINANCE_TERMS:
        if re.fullmatch(r"[a-z]+", term):
            if re.search(rf"\b{term}", lowered):
                hits.append(term)
        elif term in text:
            hits.append(term)
    return hits


def decide_disclaimer(text: str, llm_type: str | None, llm_reason: str = "", override: str | None = None) -> dict:
    hits = finance_hits(text)
    rule_on = len(hits) >= 2 or any(h in ("比特币", "以太坊", "币圈", "btc", "eth", "crypto", "bitcoin") for h in hits)
    llm_on = llm_type in FINANCE_TYPES if llm_type else False
    if override in ("on", "off"):
        on, source = override == "on", f"命令行强制 --disclaimer {override}"
    else:
        on = rule_on or llm_on
        source = "自动判断"
    reasons = [
        f"关键词规则：{'命中 ' + '、'.join(hits) if hits else '未命中财经/加密词汇'} → {'需要' if rule_on else '不需要'}",
        f"内容分类（Claude）：{llm_type or '未提供'}{'（' + llm_reason + '）' if llm_reason else ''} → {'需要' if llm_on else '不需要'}",
    ]
    return {"on": on, "source": source, "reasons": reasons, "keyword_hits": hits, "llm_type": llm_type}
