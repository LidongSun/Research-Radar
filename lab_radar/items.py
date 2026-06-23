from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RadarItem:
    source: str
    external_id: str
    title: str
    url: str
    authors_or_owner: str
    abstract_or_description: str
    published_at: str
    fetched_at: str
    raw_score: float = 0.0
    relevance_score: float = 0.0
    novelty_score: float = 0.0
    impact_score: float = 0.0
    action_score: float = 0.0
    category: str = "noise"
    summary: str = ""
    reason: str = ""
    action_suggestion: str = ""

    @classmethod
    def from_row(cls, row: Any) -> "RadarItem":
        return cls(
            source=row["source"],
            external_id=row["external_id"],
            title=row["title"],
            url=row["url"],
            authors_or_owner=row["authors_or_owner"] or "",
            abstract_or_description=row["abstract_or_description"] or "",
            published_at=row["published_at"] or "",
            fetched_at=row["fetched_at"],
            raw_score=float(row["raw_score"] or 0),
            relevance_score=float(row["relevance_score"] or 0),
            novelty_score=float(row["novelty_score"] or 0),
            impact_score=float(row["impact_score"] or 0),
            action_score=float(row["action_score"] or 0),
            category=row["category"] or "noise",
            summary=row["summary"] or "",
            reason=row["reason"] or "",
            action_suggestion=row["action_suggestion"] or "",
        )
