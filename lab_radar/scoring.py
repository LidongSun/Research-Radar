from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from lab_radar.config import LabRadarConfig
from lab_radar.items import RadarItem


def score_item(item: RadarItem, config: LabRadarConfig) -> RadarItem:
    text = f"{item.title}\n{item.authors_or_owner}\n{item.abstract_or_description}".lower()
    core_hits = _keyword_hits(text, config.core_keywords)
    adjacent_hits = _keyword_hits(text, config.adjacent_keywords)
    author_hits = _keyword_hits(text, config.watched_authors)

    relevance = min(100.0, core_hits * 22 + adjacent_hits * 10 + author_hits * 18)
    novelty = _novelty_score(item.published_at)
    impact = _impact_score(item)
    action = min(100.0, relevance * 0.55 + novelty * 0.25 + impact * 0.20)

    item.relevance_score = round(relevance, 1)
    item.novelty_score = round(novelty, 1)
    item.impact_score = round(impact, 1)
    item.action_score = round(action, 1)
    item.category = _category(relevance, action)
    item.summary = _local_summary(item)
    item.reason = _reason(core_hits, adjacent_hits, author_hits, item)
    item.action_suggestion = _action_suggestion(item)
    return item


def _keyword_hits(text: str, keywords: list[str]) -> int:
    hits = 0
    for keyword in keywords:
        normalized = keyword.lower()
        pattern = r"\b" + re.escape(normalized).replace(r"\ ", r"\s+") + r"\b"
        if re.search(pattern, text):
            hits += 1
    return hits


def _novelty_score(published_at: str) -> float:
    if not published_at:
        return 35.0
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return 35.0
    days = max(0, (datetime.now(timezone.utc) - dt).days)
    if days <= 3:
        return 100.0
    if days <= 14:
        return 75.0
    if days <= 45:
        return 50.0
    return 25.0


def _impact_score(item: RadarItem) -> float:
    if item.source == "github":
        return min(100.0, math.log10(item.raw_score + 1) * 22)
    if item.source == "huggingface":
        return min(100.0, math.log10(item.raw_score + 1) * 18)
    return 45.0


def _category(relevance: float, action: float) -> str:
    if relevance >= 55 and action >= 60:
        return "core"
    if relevance >= 30:
        return "adjacent"
    if action >= 45:
        return "wildcard"
    return "noise"


def _local_summary(item: RadarItem) -> str:
    description = item.abstract_or_description.strip()
    if not description:
        return "暂无摘要，建议打开原始链接查看。"
    return description[:220] + ("..." if len(description) > 220 else "")


def _reason(core_hits: int, adjacent_hits: int, author_hits: int, item: RadarItem) -> str:
    parts: list[str] = []
    if core_hits:
        parts.append(f"命中 {core_hits} 个核心关键词")
    if adjacent_hits:
        parts.append(f"命中 {adjacent_hits} 个邻近关键词")
    if author_hits:
        parts.append("包含关注作者")
    if item.source in {"github", "huggingface"} and item.raw_score:
        parts.append(f"公开热度分 {item.raw_score:.0f}")
    return "；".join(parts) if parts else "与当前配置的研究画像关联较弱"


def _action_suggestion(item: RadarItem) -> str:
    if item.category == "core":
        if item.source == "arxiv":
            return "建议今天精读摘要和方法部分，判断是否进入论文阅读清单。"
        if item.source == "github":
            return "建议打开 README，确认依赖和 demo，可考虑 clone 跑最小示例。"
        return "建议查看模型卡和示例，判断是否能接入你的实验流。"
    if item.category == "adjacent":
        return "建议加入本周回顾，寻找可迁移的方法或 benchmark。"
    if item.category == "wildcard":
        return "建议放入灵感池，暂不占用今天深度阅读时间。"
    return "建议忽略，除非它与你当前课题有额外隐藏关系。"
