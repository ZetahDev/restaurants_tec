from __future__ import annotations

import argparse
from datetime import datetime

from src.alerts.detector import run_alert_detection
from src.analysis.llm_analyzer import analyze_pending_reviews
from src.core.db import session_scope
from src.etl.pipeline import run_etl
from src.scripts.seed import seed_customer_surveys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FeedbackIQ CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed", help="Seed customer surveys table")
    seed_parser.add_argument("--total", type=int, default=220, help="Base generated surveys before forced cases")

    etl_parser = subparsers.add_parser("etl", help="Run ETL pipeline")
    etl_parser.add_argument("--since", type=str, default=None, help="ISO-8601 UTC timestamp")

    analyze_parser = subparsers.add_parser("analyze", help="Run LLM analysis for pending reviews")
    analyze_parser.add_argument("--limit", type=int, default=100)

    alerts_parser = subparsers.add_parser("alerts", help="Run alert detection")
    alerts_parser.add_argument("--now", type=str, default=None, help="ISO-8601 UTC timestamp")

    for command in ("report", "run-all"):
        subparsers.add_parser(command)

    return parser


def cmd_seed(total: int) -> None:
    with session_scope() as session:
        stats = seed_customer_surveys(session=session, total=total)
    print(f"Seed complete. Inserted surveys: {stats.inserted}")


def cmd_etl(since: str | None) -> None:
    since_dt = datetime.fromisoformat(since) if since else None
    stats = run_etl(since=since_dt)
    print(
        "ETL complete | "
        f"api={stats.api_extracted} survey={stats.survey_extracted} "
        f"transformed={stats.transformed} loaded={stats.loaded} dead_letters={stats.dead_letters}"
    )
    if stats.errors:
        print("Errors:")
        for err in stats.errors:
            print(f"- {err}")


def cmd_analyze(limit: int) -> None:
    stats = analyze_pending_reviews(limit=limit)
    print(
        "Analysis complete | "
        f"pending={stats.pending} analyzed={stats.analyzed} stored={stats.stored} dead_letters={stats.dead_letters}"
    )
    if stats.errors:
        print("Errors:")
        for err in stats.errors:
            print(f"- {err}")


def cmd_alerts(now: str | None) -> None:
    now_dt = datetime.fromisoformat(now) if now else None
    stats = run_alert_detection(now=now_dt)
    print(
        "Alerts complete | "
        f"generated={stats.generated} persisted={stats.persisted} notified={stats.notified}"
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "seed":
        cmd_seed(total=args.total)
        return

    if args.command == "etl":
        cmd_etl(since=args.since)
        return

    if args.command == "analyze":
        cmd_analyze(limit=args.limit)
        return

    if args.command == "alerts":
        cmd_alerts(now=args.now)
        return

    print(f"Command '{args.command}' is scaffolded and will be implemented in next commits.")


if __name__ == "__main__":
    main()
