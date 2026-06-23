from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from lab_radar.literature import search_literature


DB_PATH = Path("data/lab_radar.db")
REPORTS_DIR = Path("reports")


def serve_dashboard(host: str = "127.0.0.1", port: int = 8765) -> None:
    init_app_schema()
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Lab Radar dashboard: http://{host}:{port}")
    server.serve_forever()


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "LabRadar/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(INDEX_HTML)
            return
        if parsed.path == "/api/summary":
            self._send_json(load_summary())
            return
        if parsed.path == "/api/items":
            query = parse_qs(parsed.query)
            self._send_json(load_items(query))
            return
        if parsed.path == "/api/reports":
            self._send_json(load_reports())
            return
        if parsed.path == "/api/item-dates":
            self._send_json(available_item_dates())
            return
        if parsed.path == "/api/report/latest":
            self._send_json(load_latest_report())
            return
        if parsed.path == "/api/report":
            query = parse_qs(parsed.query)
            self._send_json(load_report(query.get("date", [""])[0]))
            return
        if parsed.path == "/api/literature/search":
            query = parse_qs(parsed.query)
            self._send_json(
                search_literature(
                    query.get("q", [""])[0],
                    query.get("source", ["all"])[0],
                    int(query.get("limit", ["8"])[0]),
                )
            )
            return
        if parsed.path == "/api/literature/saved":
            self._send_json(load_saved_literature())
            return
        if parsed.path == "/api/ideas":
            self._send_json(load_ideas())
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if parsed.path == "/api/items/status":
            update_status(payload.get("source"), payload.get("external_id"), payload.get("status"))
            self._send_json({"ok": True})
            return
        if parsed.path == "/api/literature/save":
            self._send_json(save_literature(payload))
            return
        if parsed.path == "/api/ideas":
            self._send_json(save_idea(payload))
            return
        if parsed.path == "/api/ideas/status":
            update_idea_status(payload.get("id"), payload.get("status"))
            self._send_json({"ok": True})
            return
        self.send_error(404)

    def log_message(self, format: str, *args) -> None:
        return

    def _send_html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, payload) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_app_schema() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS saved_literature (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                authors TEXT,
                year TEXT,
                venue TEXT,
                abstract TEXT,
                doi TEXT,
                external_id TEXT,
                note TEXT DEFAULT '',
                status TEXT DEFAULT 'saved',
                created_at TEXT NOT NULL,
                UNIQUE(source, external_id, title)
            );

            CREATE TABLE IF NOT EXISTS ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                note TEXT NOT NULL,
                source_type TEXT DEFAULT '',
                source_ref TEXT DEFAULT '',
                source_title TEXT DEFAULT '',
                source_url TEXT DEFAULT '',
                status TEXT DEFAULT 'open',
                created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()


def load_summary() -> dict:
    if not DB_PATH.exists():
        return {"total": 0, "by_source": [], "by_category": [], "top": []}
    with connect() as conn:
        total = conn.execute("SELECT count(*) FROM items").fetchone()[0]
        by_source = [dict(row) for row in conn.execute("SELECT source, count(*) AS count FROM items GROUP BY source")]
        by_category = [
            dict(row)
            for row in conn.execute("SELECT category, count(*) AS count FROM items GROUP BY category")
        ]
        top = [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT * FROM items
                WHERE status != 'ignored' AND category != 'noise'
                ORDER BY action_score DESC, fetched_at DESC
                LIMIT 6
                """
            )
        ]
    return {"total": total, "by_source": by_source, "by_category": by_category, "top": top}


def load_items(query: dict[str, list[str]]) -> list[dict]:
    if not DB_PATH.exists():
        return []
    source = query.get("source", ["all"])[0]
    category = query.get("category", ["all"])[0]
    date_filter = query.get("date", ["all"])[0]
    status = query.get("status", ["active"])[0]
    search = query.get("q", [""])[0].strip().lower()
    clauses = []
    params: list[str] = []
    if status == "active":
        clauses.append("status != 'ignored'")
    elif status != "all":
        clauses.append("status = ?")
        params.append(status)
    if source != "all":
        clauses.append("source = ?")
        params.append(source)
    if category != "all":
        clauses.append("category = ?")
        params.append(category)
    if date_filter != "all":
        clauses.append("substr(fetched_at, 1, 10) = ?")
        params.append(date_filter)
    if search:
        clauses.append("(lower(title) LIKE ? OR lower(abstract_or_description) LIKE ? OR lower(authors_or_owner) LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])
    sql = f"""
        SELECT * FROM items
        WHERE {' AND '.join(clauses) if clauses else '1 = 1'}
        ORDER BY action_score DESC, fetched_at DESC
        LIMIT 120
    """
    with connect() as conn:
        return [row_to_dict(row) for row in conn.execute(sql, params)]


def load_reports() -> list[dict]:
    if not REPORTS_DIR.exists():
        return []
    reports = sorted(REPORTS_DIR.glob("*.md"), reverse=True)
    result = []
    for report in reports:
        content = report.read_text(encoding="utf-8")
        result.append(
            {
                "date": report.stem,
                "path": str(report),
                "title": first_heading(content) or report.stem,
                "preview": compact_preview(content),
            }
        )
    return result


def load_latest_report() -> dict:
    if not REPORTS_DIR.exists():
        return {"path": "", "content": ""}
    reports = sorted(REPORTS_DIR.glob("*.md"), reverse=True)
    if not reports:
        return {"path": "", "content": ""}
    latest = reports[0]
    return {"path": str(latest), "content": latest.read_text(encoding="utf-8")}


def load_report(report_date: str) -> dict:
    if not report_date:
        return load_latest_report()
    path = REPORTS_DIR / f"{report_date}.md"
    if not path.exists():
        return {"path": "", "content": ""}
    return {"path": str(path), "content": path.read_text(encoding="utf-8")}


def update_status(source: str, external_id: str, status: str) -> None:
    if status not in {"new", "read", "saved", "ignored"}:
        raise ValueError("Invalid status")
    with connect() as conn:
        conn.execute(
            "UPDATE items SET status = ? WHERE source = ? AND external_id = ?",
            (status, source, external_id),
        )
        conn.commit()


def save_literature(payload: dict) -> dict:
    init_app_schema()
    now = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO saved_literature (
                source, title, url, authors, year, venue, abstract,
                doi, external_id, note, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'saved', ?)
            ON CONFLICT(source, external_id, title) DO UPDATE SET
                url = excluded.url,
                authors = excluded.authors,
                year = excluded.year,
                venue = excluded.venue,
                abstract = excluded.abstract,
                doi = excluded.doi,
                note = CASE
                    WHEN excluded.note != '' THEN excluded.note
                    ELSE saved_literature.note
                END,
                status = 'saved'
            """,
            (
                payload.get("source", ""),
                payload.get("title", "Untitled"),
                payload.get("url", ""),
                payload.get("authors", ""),
                str(payload.get("year", "")),
                payload.get("venue", ""),
                payload.get("abstract", ""),
                payload.get("doi", ""),
                payload.get("external_id", "") or payload.get("doi", "") or payload.get("url", ""),
                payload.get("note", ""),
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM saved_literature WHERE source = ? AND external_id = ? AND title = ?",
            (
                payload.get("source", ""),
                payload.get("external_id", "") or payload.get("doi", "") or payload.get("url", ""),
                payload.get("title", "Untitled"),
            ),
        ).fetchone()
    return row_to_dict(row) if row else {"ok": True}


def load_saved_literature() -> list[dict]:
    init_app_schema()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM saved_literature
            WHERE status != 'ignored'
            ORDER BY created_at DESC
            LIMIT 200
            """
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def save_idea(payload: dict) -> dict:
    init_app_schema()
    now = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO ideas (
                title, note, source_type, source_ref, source_title,
                source_url, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (
                payload.get("title", "Untitled idea"),
                payload.get("note", ""),
                payload.get("source_type", ""),
                payload.get("source_ref", ""),
                payload.get("source_title", ""),
                payload.get("source_url", ""),
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM ideas WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_dict(row)


def load_ideas() -> list[dict]:
    init_app_schema()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM ideas
            WHERE status != 'archived'
            ORDER BY created_at DESC
            LIMIT 200
            """
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def update_idea_status(idea_id, status: str) -> None:
    if status not in {"open", "doing", "done", "archived"}:
        raise ValueError("Invalid idea status")
    with connect() as conn:
        conn.execute("UPDATE ideas SET status = ? WHERE id = ?", (status, idea_id))
        conn.commit()


def row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}


def first_heading(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def compact_preview(content: str) -> str:
    lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped == "---":
            continue
        lines.append(stripped)
        if len(" ".join(lines)) > 120:
            break
    return " ".join(lines)[:180]


def available_item_dates() -> list[str]:
    if not DB_PATH.exists():
        return []
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT substr(fetched_at, 1, 10) AS date
            FROM items
            ORDER BY date DESC
            """
        ).fetchall()
    return [row["date"] for row in rows if row["date"]]


INDEX_HTML = r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Lab Radar</title>
  <style>
    :root {
      --paper: #f7f4ed;
      --ink: #171713;
      --muted: #6d695f;
      --line: #ded8ca;
      --panel: #fffdf7;
      --coal: #24231f;
      --accent: #d24b2a;
      --accent-2: #167c80;
      --green: #2f7d4f;
      --gold: #9b6b1e;
      --shadow: 0 24px 70px rgba(36, 35, 31, .12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        linear-gradient(135deg, rgba(210,75,42,.08), transparent 28%),
        linear-gradient(315deg, rgba(22,124,128,.10), transparent 34%),
        var(--paper);
      font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
      letter-spacing: 0;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: .35;
      background-image: linear-gradient(rgba(23,23,19,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(23,23,19,.03) 1px, transparent 1px);
      background-size: 28px 28px;
      mask-image: linear-gradient(to bottom, #000, transparent 80%);
    }
    button, input, select { font: inherit; }
    .shell { max-width: 1440px; margin: 0 auto; padding: 28px; }
    header {
      min-height: 220px;
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(320px, .9fr);
      gap: 24px;
      align-items: stretch;
      border-bottom: 1px solid rgba(23,23,19,.12);
      padding-bottom: 24px;
    }
    .brand {
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      padding: 6px 0;
    }
    .eyebrow {
      width: fit-content;
      border: 1px solid var(--ink);
      border-radius: 999px;
      padding: 7px 11px;
      font-size: 12px;
      color: var(--ink);
      background: rgba(255,253,247,.56);
    }
    h1 {
      margin: 28px 0 12px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 88px;
      line-height: .88;
      font-weight: 700;
      letter-spacing: 0;
    }
    .subhead {
      max-width: 760px;
      color: var(--muted);
      font-size: 17px;
      line-height: 1.65;
    }
    .command {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      align-content: start;
    }
    .metric {
      min-height: 104px;
      border: 1px solid var(--line);
      background: rgba(255,253,247,.72);
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 8px 24px rgba(36,35,31,.06);
    }
    .metric strong { display: block; font-size: 34px; line-height: 1; }
    .metric span { display: block; margin-top: 10px; color: var(--muted); font-size: 13px; }
    .metric.accent {
      background: var(--coal);
      color: #fff8e8;
      border-color: var(--coal);
    }
    .toolbar {
      position: sticky;
      top: 0;
      z-index: 5;
      display: grid;
      grid-template-columns: 1fr auto auto auto;
      gap: 10px;
      align-items: center;
      padding: 16px 0;
      backdrop-filter: blur(14px);
    }
    .literature-panel {
      border: 1px solid var(--line);
      background: rgba(255,253,247,.88);
      border-radius: 8px;
      padding: 16px;
      margin: 0 0 18px;
      box-shadow: 0 10px 30px rgba(36,35,31,.06);
    }
    .literature-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 12px;
    }
    .literature-head h2 {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 28px;
    }
    .literature-head span {
      color: var(--muted);
      font-size: 13px;
    }
    .literature-form {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 190px 112px;
      gap: 10px;
      margin-bottom: 14px;
    }
    .primary-btn {
      height: 42px;
      border: 1px solid var(--coal);
      border-radius: 8px;
      color: #fff8e8;
      background: var(--coal);
      cursor: pointer;
    }
    .primary-btn:hover { background: var(--accent); border-color: var(--accent); }
    .literature-results {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .paper-card {
      min-height: 210px;
      border: 1px solid rgba(23,23,19,.12);
      background: rgba(255,253,247,.72);
      border-radius: 8px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .paper-card h3 {
      margin: 0;
      font-size: 17px;
      line-height: 1.35;
    }
    .paper-card h3 a { color: var(--ink); text-decoration: none; }
    .paper-card h3 a:hover { color: var(--accent); }
    .paper-meta, .paper-abstract {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .paper-abstract { color: #3a372f; }
    .external-links {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }
    .external-links a {
      border: 1px solid rgba(23,23,19,.14);
      border-radius: 999px;
      color: var(--ink);
      background: rgba(255,253,247,.72);
      padding: 7px 10px;
      text-decoration: none;
      font-size: 12px;
    }
    .external-links a:hover { background: var(--coal); color: #fff8e8; }
    .workspace-nav {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin: 0 0 16px;
    }
    .workspace-nav button {
      height: 40px;
      border: 1px solid rgba(23,23,19,.16);
      background: rgba(255,253,247,.82);
      color: var(--ink);
      border-radius: 8px;
      padding: 0 13px;
      cursor: pointer;
    }
    .workspace-nav button.active {
      background: var(--coal);
      color: #fff8e8;
      border-color: var(--coal);
    }
    .workspace-section { display: none; }
    .workspace-section.active { display: block; }
    .library-controls {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin: 0 0 14px;
    }
    .idea-form {
      display: grid;
      grid-template-columns: minmax(220px, .6fr) minmax(260px, 1fr) 108px;
      gap: 10px;
      margin-bottom: 14px;
    }
    .idea-form textarea {
      min-height: 42px;
      resize: vertical;
      border: 1px solid rgba(23,23,19,.16);
      background: rgba(255,253,247,.84);
      color: var(--ink);
      border-radius: 8px;
      padding: 10px 12px;
      outline: none;
      font: inherit;
    }
    .idea-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .idea-card {
      border: 1px solid var(--line);
      background: rgba(255,253,247,.88);
      border-radius: 8px;
      padding: 15px;
      min-height: 170px;
    }
    .idea-card h3 { margin: 0 0 8px; font-size: 18px; }
    .idea-card p { color: #3a372f; line-height: 1.55; font-size: 14px; }
    .status-pill {
      display: inline-flex;
      align-items: center;
      height: 24px;
      border-radius: 999px;
      padding: 0 9px;
      background: #ebe5d7;
      color: var(--muted);
      font-size: 12px;
    }
    .search, select {
      height: 42px;
      border: 1px solid rgba(23,23,19,.16);
      background: rgba(255,253,247,.84);
      color: var(--ink);
      border-radius: 8px;
      padding: 0 12px;
      outline: none;
    }
    .search:focus, select:focus, button:focus { box-shadow: 0 0 0 3px rgba(210,75,42,.18); }
    .tabs { display: flex; gap: 8px; flex-wrap: wrap; }
    .tab, .icon-btn {
      height: 42px;
      border: 1px solid rgba(23,23,19,.16);
      background: rgba(255,253,247,.82);
      border-radius: 8px;
      padding: 0 13px;
      cursor: pointer;
      color: var(--ink);
    }
    .tab.active {
      color: #fff8e8;
      background: var(--coal);
      border-color: var(--coal);
    }
    main {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 360px;
      gap: 22px;
      align-items: start;
    }
    .section-title {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      margin: 8px 0 12px;
    }
    .section-title h2 {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 30px;
      letter-spacing: 0;
    }
    .section-title span { color: var(--muted); font-size: 13px; }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .item {
      min-height: 282px;
      display: flex;
      flex-direction: column;
      border: 1px solid var(--line);
      background: rgba(255,253,247,.88);
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 10px 30px rgba(36,35,31,.06);
      transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease;
    }
    .item:hover { transform: translateY(-2px); box-shadow: var(--shadow); border-color: rgba(36,35,31,.32); }
    .item-top { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
    .badge {
      height: 26px;
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 0 9px;
      font-size: 12px;
      color: #fff8e8;
      background: var(--coal);
      white-space: nowrap;
    }
    .badge.core { background: var(--accent); }
    .badge.adjacent { background: var(--accent-2); }
    .badge.wildcard { background: var(--gold); }
    .source { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
    .item h3 {
      margin: 0 0 10px;
      font-size: 19px;
      line-height: 1.28;
      letter-spacing: 0;
    }
    .item h3 a { color: var(--ink); text-decoration: none; }
    .item h3 a:hover { color: var(--accent); }
    .meta { color: var(--muted); font-size: 13px; line-height: 1.45; margin-bottom: 12px; }
    .summary {
      color: #36342d;
      font-size: 14px;
      line-height: 1.55;
      margin: 0 0 14px;
      flex: 1;
    }
    .bars { display: grid; gap: 7px; margin: 10px 0 14px; }
    .bar { display: grid; grid-template-columns: 50px 1fr 42px; gap: 8px; align-items: center; color: var(--muted); font-size: 12px; }
    .track { height: 7px; background: #ebe5d7; border-radius: 99px; overflow: hidden; }
    .fill { height: 100%; width: 0; background: var(--accent); border-radius: 99px; }
    .actions { display: flex; gap: 8px; margin-top: auto; }
    .actions button, .actions a {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 38px;
      height: 36px;
      border-radius: 8px;
      border: 1px solid rgba(23,23,19,.16);
      background: #fffdf7;
      color: var(--ink);
      text-decoration: none;
      cursor: pointer;
    }
    .actions button:hover, .actions a:hover { background: var(--coal); color: #fff8e8; }
    aside {
      position: sticky;
      top: 74px;
      display: grid;
      gap: 14px;
    }
    .side-panel {
      border: 1px solid var(--line);
      background: rgba(255,253,247,.84);
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 10px 30px rgba(36,35,31,.06);
    }
    .side-panel h2 {
      margin: 0 0 14px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 24px;
    }
    .signal { display: grid; gap: 11px; }
    .signal-row { display: grid; grid-template-columns: 96px 1fr 32px; gap: 8px; align-items: center; font-size: 13px; color: var(--muted); }
    .mini-track { height: 8px; border-radius: 99px; background: #e8e0cf; overflow: hidden; }
    .mini-fill { height: 100%; background: var(--accent-2); }
    .top-list { display: grid; gap: 11px; }
    .top-item { padding-bottom: 11px; border-bottom: 1px solid rgba(23,23,19,.10); }
    .top-item:last-child { border-bottom: 0; padding-bottom: 0; }
    .top-item a { color: var(--ink); font-weight: 650; text-decoration: none; line-height: 1.35; }
    .top-item p { margin: 5px 0 0; color: var(--muted); font-size: 12px; }
    .report {
      max-height: 360px;
      overflow: auto;
      white-space: pre-wrap;
      color: #3a372f;
      font-size: 12px;
      line-height: 1.55;
      border-top: 1px solid rgba(23,23,19,.10);
      padding-top: 12px;
    }
    .history-list {
      display: grid;
      gap: 10px;
      max-height: 300px;
      overflow: auto;
    }
    .history-item {
      width: 100%;
      text-align: left;
      border: 1px solid rgba(23,23,19,.12);
      background: rgba(255,253,247,.72);
      border-radius: 8px;
      padding: 11px;
      cursor: pointer;
      color: var(--ink);
    }
    .history-item:hover, .history-item.active {
      background: var(--coal);
      color: #fff8e8;
      border-color: var(--coal);
    }
    .history-item strong {
      display: block;
      font-size: 13px;
      margin-bottom: 5px;
    }
    .history-item span {
      display: block;
      color: inherit;
      opacity: .72;
      font-size: 12px;
      line-height: 1.4;
    }
    .empty {
      border: 1px dashed rgba(23,23,19,.22);
      border-radius: 8px;
      padding: 28px;
      color: var(--muted);
      background: rgba(255,253,247,.52);
    }
    @media (max-width: 1180px) {
      header, main { grid-template-columns: 1fr; }
      aside { position: static; grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 760px) {
      .shell { padding: 18px; }
      header { min-height: auto; }
      h1 { font-size: 48px; }
      .command, .grid, aside { grid-template-columns: 1fr; }
      .literature-form, .literature-results, .idea-form, .idea-grid { grid-template-columns: 1fr; }
      .toolbar { position: static; grid-template-columns: 1fr; }
      .tabs { width: 100%; }
      .tab { flex: 1; min-width: 86px; }
      .item { min-height: auto; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div class="brand">
        <div>
          <div class="eyebrow">Research Radar · Open Source Sentinel</div>
          <h1>Lab Radar</h1>
          <p class="subhead">AI Robotics Research Intelligence</p>
        </div>
      </div>
      <div class="command" id="metrics"></div>
    </header>

    <div class="toolbar">
      <input class="search" id="search" placeholder="搜索论文、repo、作者、关键词" />
      <select id="source">
        <option value="all">全部来源</option>
        <option value="arxiv">arXiv</option>
        <option value="github">GitHub</option>
        <option value="huggingface">Hugging Face</option>
      </select>
      <select id="date-filter">
        <option value="all">全部日期</option>
      </select>
      <div class="tabs" id="tabs">
        <button class="tab active" data-category="all">全部</button>
        <button class="tab" data-category="core">Core</button>
        <button class="tab" data-category="adjacent">Adjacent</button>
        <button class="tab" data-category="wildcard">Wildcard</button>
      </div>
    </div>

    <section class="literature-panel">
      <div class="literature-head">
        <h2>Literature Search</h2>
        <span>arXiv · OpenAlex · Crossref · Semantic Scholar · PubMed · Europe PMC</span>
      </div>
      <div class="literature-form">
        <input class="search" id="literature-query" placeholder="Search papers, e.g. diffusion policy robot learning" />
        <select id="literature-source">
          <option value="all">All indexes</option>
          <option value="arxiv">arXiv</option>
          <option value="openalex">OpenAlex</option>
          <option value="crossref">Crossref</option>
          <option value="semantic_scholar">Semantic Scholar</option>
          <option value="pubmed">PubMed</option>
          <option value="europe_pmc">Europe PMC</option>
        </select>
        <button class="primary-btn" id="literature-button">Search</button>
      </div>
      <div class="literature-results" id="literature-results"></div>
      <div class="external-links" id="external-links"></div>
    </section>

    <div class="workspace-nav" id="workspace-nav">
      <button class="active" data-view="radar">Radar</button>
      <button data-view="library">Library</button>
      <button data-view="ideas">Ideas</button>
    </div>

    <main>
      <section class="workspace-section active" id="view-radar">
        <div class="section-title">
          <h2>今日情报</h2>
          <span id="item-count"></span>
        </div>
        <div class="grid" id="items"></div>
      </section>

      <section class="workspace-section" id="view-library">
        <div class="section-title">
          <h2>Library</h2>
          <span id="library-count"></span>
        </div>
        <div class="library-controls" id="library-tabs">
          <button class="tab active" data-library-status="saved">收藏</button>
          <button class="tab" data-library-status="new">待读</button>
          <button class="tab" data-library-status="read">已读</button>
          <button class="tab" data-library-status="papers">本地文献库</button>
        </div>
        <div class="grid" id="library-items"></div>
      </section>

      <section class="workspace-section" id="view-ideas">
        <div class="section-title">
          <h2>Idea Backlog</h2>
          <span id="idea-count"></span>
        </div>
        <div class="idea-form">
          <input class="search" id="idea-title" placeholder="Idea title" />
          <textarea id="idea-note" placeholder="Why it matters, possible experiment, next action"></textarea>
          <button class="primary-btn" id="idea-add">Add</button>
        </div>
        <div class="idea-grid" id="idea-list"></div>
      </section>

      <aside>
        <section class="side-panel">
          <h2>优先行动</h2>
          <div class="top-list" id="top-list"></div>
        </section>
        <section class="side-panel">
          <h2>信号分布</h2>
          <div class="signal" id="signals"></div>
        </section>
        <section class="side-panel">
          <h2>最新日报</h2>
          <div class="history-list" id="history-list"></div>
          <div class="report" id="report"></div>
        </section>
      </aside>
    </main>
  </div>

  <script>
    const state = { category: "all", source: "all", date: "all", q: "", reportDate: "", view: "radar", libraryStatus: "saved" };
    let lastLiteratureResults = [];
    const labels = { arxiv: "论文", github: "开源", huggingface: "模型" };
    const categoryNames = { core: "Core", adjacent: "Adjacent", wildcard: "Wildcard", noise: "Noise" };

    const $ = (id) => document.getElementById(id);
    const clamp = (value) => Math.max(0, Math.min(100, Number(value || 0)));

    async function api(path, options) {
      const res = await fetch(path, options);
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    }

    async function load() {
      const [summary, items, reports, itemDates, report] = await Promise.all([
        api("/api/summary"),
        api(`/api/items?source=${state.source}&category=${state.category}&date=${state.date}&q=${encodeURIComponent(state.q)}`),
        api("/api/reports"),
        api("/api/item-dates"),
        api(state.reportDate ? `/api/report?date=${state.reportDate}` : "/api/report/latest")
      ]);
      renderMetrics(summary);
      renderItems(items);
      renderTop(summary.top || []);
      renderSignals(summary);
      renderDates(itemDates);
      renderHistory(reports);
      $("report").textContent = report.content ? report.content.slice(0, 1800) : "暂无日报";
      if (state.view === "library") loadLibrary();
      if (state.view === "ideas") loadIdeas();
    }

    function renderMetrics(summary) {
      const sourceMap = Object.fromEntries((summary.by_source || []).map(x => [x.source, x.count]));
      const categoryMap = Object.fromEntries((summary.by_category || []).map(x => [x.category, x.count]));
      $("metrics").innerHTML = [
        metric(summary.total || 0, "总监控条目", "accent"),
        metric(categoryMap.core || 0, "Core 信号"),
        metric(sourceMap.github || 0, "开源项目"),
        metric(sourceMap.arxiv || 0, "论文候选")
      ].join("");
    }

    function metric(value, label, extra = "") {
      return `<div class="metric ${extra}"><strong>${value}</strong><span>${label}</span></div>`;
    }

    function renderItems(items) {
      $("item-count").textContent = `${items.length} 条`;
      if (!items.length) {
        $("items").innerHTML = `<div class="empty">当前筛选下没有高相关条目。</div>`;
        return;
      }
      $("items").innerHTML = items.map(itemCard).join("");
    }

    function itemCard(item) {
      const title = escapeHtml(item.title || "Untitled");
      const owner = escapeHtml(item.authors_or_owner || "未知");
      const summary = escapeHtml(item.summary || item.abstract_or_description || "暂无摘要");
      return `
        <article class="item">
          <div class="item-top">
            <span class="source">${labels[item.source] || item.source}</span>
            <span class="badge ${item.category}">${categoryNames[item.category] || item.category}</span>
          </div>
          <h3><a href="${item.url}" target="_blank" rel="noreferrer">${title}</a></h3>
          <div class="meta">${owner}</div>
          <p class="summary">${summary}</p>
          <div class="bars">
            ${bar("相关", item.relevance_score)}
            ${bar("新颖", item.novelty_score)}
            ${bar("行动", item.action_score)}
          </div>
          <div class="actions">
            <a href="${item.url}" target="_blank" rel="noreferrer" title="打开原文">↗</a>
            <button title="标记已读" onclick='setStatus(${JSON.stringify(item.source)}, ${JSON.stringify(item.external_id)}, "read")'>✓</button>
            <button title="收藏" onclick='setStatus(${JSON.stringify(item.source)}, ${JSON.stringify(item.external_id)}, "saved")'>★</button>
            <button title="加入 Idea" onclick='ideaFromItem(${JSON.stringify(item.source)}, ${JSON.stringify(item.external_id)}, ${JSON.stringify(item.title)}, ${JSON.stringify(item.url)})'>＋</button>
            <button title="忽略" onclick='setStatus(${JSON.stringify(item.source)}, ${JSON.stringify(item.external_id)}, "ignored")'>×</button>
          </div>
        </article>
      `;
    }

    function bar(label, value) {
      const width = clamp(value);
      return `<div class="bar"><span>${label}</span><div class="track"><div class="fill" style="width:${width}%"></div></div><span>${width.toFixed(0)}</span></div>`;
    }

    function renderTop(items) {
      $("top-list").innerHTML = items.length ? items.map(item => `
        <div class="top-item">
          <a href="${item.url}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a>
          <p>${labels[item.source] || item.source} · 行动 ${Number(item.action_score || 0).toFixed(1)}</p>
        </div>
      `).join("") : `<div class="empty">暂无优先行动。</div>`;
    }

    function renderSignals(summary) {
      const rows = [...(summary.by_category || [])].sort((a, b) => b.count - a.count);
      const max = Math.max(...rows.map(x => x.count), 1);
      $("signals").innerHTML = rows.map(row => `
        <div class="signal-row">
          <span>${categoryNames[row.category] || row.category}</span>
          <div class="mini-track"><div class="mini-fill" style="width:${Math.round(row.count / max * 100)}%"></div></div>
          <span>${row.count}</span>
        </div>
      `).join("");
    }

    function renderDates(dates) {
      const options = [`<option value="all">全部日期</option>`].concat(
        dates.map(date => `<option value="${date}">${date}</option>`)
      );
      $("date-filter").innerHTML = options.join("");
      $("date-filter").value = [...dates, "all"].includes(state.date) ? state.date : "all";
    }

    function renderHistory(reports) {
      if (!reports.length) {
        $("history-list").innerHTML = `<div class="empty">暂无历史日报。</div>`;
        return;
      }
      $("history-list").innerHTML = reports.map(report => `
        <button class="history-item ${state.reportDate === report.date ? "active" : ""}" data-report-date="${report.date}">
          <strong>${escapeHtml(report.date)}</strong>
          <span>${escapeHtml(report.preview || report.title)}</span>
        </button>
      `).join("");
    }

    async function setStatus(source, external_id, status) {
      await api("/api/items/status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source, external_id, status })
      });
      load();
    }

    async function loadLibrary() {
      if (state.libraryStatus === "papers") {
        const papers = await api("/api/literature/saved");
        $("library-count").textContent = `${papers.length} papers`;
        $("library-items").innerHTML = papers.length ? papers.map(savedPaperCard).join("") : `<div class="empty">还没有保存文献。</div>`;
        return;
      }
      const items = await api(`/api/items?status=${state.libraryStatus}&source=all&category=all&date=all&q=`);
      $("library-count").textContent = `${items.length} items`;
      $("library-items").innerHTML = items.length ? items.map(itemCard).join("") : `<div class="empty">这个分区暂时为空。</div>`;
    }

    function savedPaperCard(paper) {
      return `
        <article class="paper-card">
          <div class="item-top">
            <span class="source">${escapeHtml(paper.source || "Paper")}</span>
            <span class="badge adjacent">${escapeHtml(paper.year || "Saved")}</span>
          </div>
          <h3><a href="${paper.url || "#"}" target="_blank" rel="noreferrer">${escapeHtml(paper.title || "Untitled")}</a></h3>
          <div class="paper-meta">${escapeHtml([paper.authors, paper.venue, paper.doi ? "DOI: " + paper.doi : ""].filter(Boolean).join(" · "))}</div>
          <div class="paper-abstract">${escapeHtml(paper.abstract || "No abstract saved.")}</div>
          <div class="actions">
            <a href="${paper.url || "#"}" target="_blank" rel="noreferrer" title="打开">↗</a>
            <button title="加入 Idea" onclick='ideaFromItem("literature", ${JSON.stringify(paper.external_id || paper.id)}, ${JSON.stringify(paper.title)}, ${JSON.stringify(paper.url || "")})'>＋</button>
          </div>
        </article>
      `;
    }

    async function loadIdeas() {
      const ideas = await api("/api/ideas");
      $("idea-count").textContent = `${ideas.length} ideas`;
      $("idea-list").innerHTML = ideas.length ? ideas.map(ideaCard).join("") : `<div class="empty">还没有 idea。可以从论文、repo、文献检索结果里添加。</div>`;
    }

    function ideaCard(idea) {
      return `
        <article class="idea-card">
          <div class="item-top">
            <span class="status-pill">${escapeHtml(idea.status || "open")}</span>
            ${idea.source_url ? `<a href="${idea.source_url}" target="_blank" rel="noreferrer">↗</a>` : ""}
          </div>
          <h3>${escapeHtml(idea.title)}</h3>
          <p>${escapeHtml(idea.note)}</p>
          <div class="meta">${escapeHtml(idea.source_title || idea.source_type || "")}</div>
          <div class="actions">
            <button title="Doing" onclick='setIdeaStatus(${idea.id}, "doing")'>…</button>
            <button title="Done" onclick='setIdeaStatus(${idea.id}, "done")'>✓</button>
            <button title="Archive" onclick='setIdeaStatus(${idea.id}, "archived")'>×</button>
          </div>
        </article>
      `;
    }

    async function addIdea(payload) {
      await api("/api/ideas", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      $("idea-title").value = "";
      $("idea-note").value = "";
      loadIdeas();
    }

    function ideaFromItem(source_type, source_ref, source_title, source_url) {
      const note = prompt("这个条目给你的科研想法是什么？");
      if (!note) return;
      addIdea({
        title: source_title,
        note,
        source_type,
        source_ref,
        source_title,
        source_url
      });
    }

    async function setIdeaStatus(id, status) {
      await api("/api/ideas/status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, status })
      });
      loadIdeas();
    }

    async function searchPapers() {
      const q = $("literature-query").value.trim();
      const source = $("literature-source").value;
      if (!q) {
        $("literature-results").innerHTML = `<div class="empty">Enter keywords to search literature.</div>`;
        $("external-links").innerHTML = "";
        return;
      }
      $("literature-button").disabled = true;
      $("literature-button").textContent = "Searching";
      $("literature-results").innerHTML = `<div class="empty">Searching open academic indexes...</div>`;
      try {
        const payload = await api(`/api/literature/search?q=${encodeURIComponent(q)}&source=${source}&limit=8`);
        lastLiteratureResults = payload.results || [];
        renderLiterature(lastLiteratureResults);
        renderExternalLinks(payload.external_links || []);
        if (payload.errors && payload.errors.length) {
          console.warn("Literature source errors", payload.errors);
        }
      } catch (error) {
        $("literature-results").innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
      } finally {
        $("literature-button").disabled = false;
        $("literature-button").textContent = "Search";
      }
    }

    function renderLiterature(results) {
      if (!results.length) {
        $("literature-results").innerHTML = `<div class="empty">No results found in the selected open indexes.</div>`;
        return;
      }
      $("literature-results").innerHTML = results.map(paper => `
        <article class="paper-card">
          <div class="item-top">
            <span class="source">${escapeHtml(paper.source || "Index")}</span>
            <span class="badge adjacent">${escapeHtml(paper.year || "Paper")}</span>
          </div>
          <h3><a href="${paper.url || "#"}" target="_blank" rel="noreferrer">${escapeHtml(paper.title || "Untitled")}</a></h3>
          <div class="paper-meta">${escapeHtml([paper.authors, paper.venue, paper.doi ? "DOI: " + paper.doi : ""].filter(Boolean).join(" · "))}</div>
          <div class="paper-abstract">${escapeHtml(paper.abstract || "No abstract available from this index.")}</div>
          <div class="actions">
            <a href="${paper.url || "#"}" target="_blank" rel="noreferrer" title="Open">↗</a>
            <button title="Save to library" onclick="saveLiterature(${results.indexOf(paper)})">★</button>
            <button title="Add idea" onclick="ideaFromLiterature(${results.indexOf(paper)})">＋</button>
          </div>
        </article>
      `).join("");
    }

    async function saveLiterature(index) {
      const paper = lastLiteratureResults[index];
      if (!paper) return;
      await api("/api/literature/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(paper)
      });
      state.view = "library";
      state.libraryStatus = "papers";
      setActiveView("library");
      setActiveLibraryTab();
      loadLibrary();
    }

    function ideaFromLiterature(index) {
      const paper = lastLiteratureResults[index];
      if (!paper) return;
      const note = prompt("这篇文献带来的 idea 是什么？");
      if (!note) return;
      addIdea({
        title: paper.title,
        note,
        source_type: "literature",
        source_ref: paper.external_id || paper.doi || paper.url,
        source_title: paper.title,
        source_url: paper.url
      });
    }

    function renderExternalLinks(links) {
      $("external-links").innerHTML = links.map(link => `
        <a href="${link.url}" target="_blank" rel="noreferrer" title="${escapeHtml(link.note || "")}">${escapeHtml(link.source)}</a>
      `).join("");
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, c => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
      }[c]));
    }

    $("search").addEventListener("input", (event) => {
      state.q = event.target.value;
      clearTimeout(window.searchTimer);
      window.searchTimer = setTimeout(load, 180);
    });
    $("source").addEventListener("change", (event) => {
      state.source = event.target.value;
      load();
    });
    $("date-filter").addEventListener("change", (event) => {
      state.date = event.target.value;
      load();
    });
    $("history-list").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-report-date]");
      if (!button) return;
      state.reportDate = button.dataset.reportDate;
      load();
    });
    $("workspace-nav").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-view]");
      if (!button) return;
      state.view = button.dataset.view;
      setActiveView(state.view);
      if (state.view === "library") loadLibrary();
      if (state.view === "ideas") loadIdeas();
    });
    $("library-tabs").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-library-status]");
      if (!button) return;
      state.libraryStatus = button.dataset.libraryStatus;
      setActiveLibraryTab();
      loadLibrary();
    });
    $("idea-add").addEventListener("click", () => {
      const title = $("idea-title").value.trim();
      const note = $("idea-note").value.trim();
      if (!title || !note) return;
      addIdea({ title, note });
    });
    function setActiveView(view) {
      document.querySelectorAll("#workspace-nav button").forEach(button => {
        button.classList.toggle("active", button.dataset.view === view);
      });
      document.querySelectorAll(".workspace-section").forEach(section => section.classList.remove("active"));
      $(`view-${view}`).classList.add("active");
    }
    function setActiveLibraryTab() {
      document.querySelectorAll("#library-tabs button").forEach(button => {
        button.classList.toggle("active", button.dataset.libraryStatus === state.libraryStatus);
      });
    }
    $("tabs").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-category]");
      if (!button) return;
      state.category = button.dataset.category;
      document.querySelectorAll(".tab").forEach(tab => tab.classList.remove("active"));
      button.classList.add("active");
      load();
    });
    $("literature-button").addEventListener("click", searchPapers);
    $("literature-query").addEventListener("keydown", (event) => {
      if (event.key === "Enter") searchPapers();
    });

    load().catch(error => {
      $("items").innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
    });
  </script>
</body>
</html>
"""
