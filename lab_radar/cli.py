from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone

from lab_radar.config import load_config
from lab_radar.db import RadarStore
from lab_radar.llm import enrich_with_llm
from lab_radar.reporter import write_daily_report
from lab_radar.scoring import score_item
from lab_radar.sources import fetch_all


def main() -> None:
    parser = argparse.ArgumentParser(description="Lab Radar research intelligence assistant")
    parser.add_argument("--config", default="config.yaml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_daily = subparsers.add_parser("run-daily", help="Fetch, score, store, and write a daily report")
    run_daily.add_argument("--date", default=date.today().isoformat())
    run_daily.add_argument("--use-llm", action="store_true")

    subparsers.add_parser("show-config", help="Print parsed config as JSON")
    serve = subparsers.add_parser("serve", help="Start the local Lab Radar dashboard")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    config = load_config(args.config)
    if args.command == "show-config":
        print(json.dumps(config.raw, ensure_ascii=False, indent=2))
        return
    if args.command == "run-daily":
        run_daily_command(config, args.date, args.use_llm)
    if args.command == "serve":
        from lab_radar.web import serve_dashboard

        serve_dashboard(args.host, args.port)


def run_daily_command(config, report_date: str, use_llm: bool) -> None:
    store = RadarStore()
    fetched = fetch_all(config)
    changed = store.upsert_items(fetched)
    items = store.recent_items(limit=300)
    scored = []
    for item in items:
        scored_item = score_item(item, config)
        if use_llm and scored_item.category in {"core", "adjacent"}:
            scored_item = enrich_with_llm(scored_item)
        store.update_scores(scored_item)
        scored.append(scored_item)
    report_path = write_daily_report(scored, config, report_date)
    summary = f"Fetched {len(fetched)} items, changed {changed}, reported {len(scored)}."
    store.save_report(report_date, str(report_path), summary, datetime.now(timezone.utc).isoformat())
    print(summary)
    print(f"Report: {report_path}")
