from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from lab_radar.items import RadarItem


SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    authors_or_owner TEXT,
    abstract_or_description TEXT,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    raw_score REAL DEFAULT 0,
    relevance_score REAL DEFAULT 0,
    novelty_score REAL DEFAULT 0,
    impact_score REAL DEFAULT 0,
    action_score REAL DEFAULT 0,
    category TEXT DEFAULT 'noise',
    summary TEXT,
    reason TEXT,
    action_suggestion TEXT,
    status TEXT DEFAULT 'new',
    UNIQUE(source, external_id)
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL UNIQUE,
    markdown_path TEXT NOT NULL,
    summary TEXT,
    created_at TEXT NOT NULL
);
"""


class RadarStore:
    def __init__(self, path: str | Path = "data/lab_radar.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def upsert_items(self, items: Iterable[RadarItem]) -> int:
        changed = 0
        for item in items:
            result = self.conn.execute(
                """
                INSERT INTO items (
                    source, external_id, title, url, authors_or_owner,
                    abstract_or_description, published_at, fetched_at, raw_score
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, external_id) DO UPDATE SET
                    title = excluded.title,
                    url = excluded.url,
                    authors_or_owner = excluded.authors_or_owner,
                    abstract_or_description = excluded.abstract_or_description,
                    published_at = excluded.published_at,
                    fetched_at = excluded.fetched_at,
                    raw_score = excluded.raw_score
                """,
                (
                    item.source,
                    item.external_id,
                    item.title,
                    item.url,
                    item.authors_or_owner,
                    item.abstract_or_description,
                    item.published_at,
                    item.fetched_at,
                    item.raw_score,
                ),
            )
            changed += result.rowcount
        self.conn.commit()
        return changed

    def update_scores(self, item: RadarItem) -> None:
        self.conn.execute(
            """
            UPDATE items
            SET relevance_score = ?, novelty_score = ?, impact_score = ?,
                action_score = ?, category = ?, summary = ?, reason = ?,
                action_suggestion = ?
            WHERE source = ? AND external_id = ?
            """,
            (
                item.relevance_score,
                item.novelty_score,
                item.impact_score,
                item.action_score,
                item.category,
                item.summary,
                item.reason,
                item.action_suggestion,
                item.source,
                item.external_id,
            ),
        )
        self.conn.commit()

    def recent_items(self, limit: int = 200) -> list[RadarItem]:
        rows = self.conn.execute(
            "SELECT * FROM items WHERE status != 'ignored' ORDER BY fetched_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [RadarItem.from_row(row) for row in rows]

    def save_report(self, report_date: str, markdown_path: str, summary: str, created_at: str) -> None:
        self.conn.execute(
            """
            INSERT INTO reports (report_date, markdown_path, summary, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(report_date) DO UPDATE SET
                markdown_path = excluded.markdown_path,
                summary = excluded.summary,
                created_at = excluded.created_at
            """,
            (report_date, markdown_path, summary, created_at),
        )
        self.conn.commit()
