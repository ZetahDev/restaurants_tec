from __future__ import annotations

import argparse
from datetime import date, datetime

from src.alerts.detector import run_alert_detection
from src.analysis.llm_analyzer import analyze_pending_reviews
from src.analysis.usage_tracker import summarize_usage
from src.core.db import session_scope
from src.etl.pipeline import run_etl
from src.reports.weekly_report import generate_weekly_report
from src.scripts.prep_demo import run_prep_demo, stats_to_json
from src.scripts.seed import seed_customer_surveys
import json


def _str_to_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError("Expected boolean value: true/false")


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

    report_parser = subparsers.add_parser("report", help="Generate weekly report")
    report_parser.add_argument("--week-start", type=str, default=None, help="YYYY-MM-DD")

    run_all_parser = subparsers.add_parser("run-all", help="Run ETL -> analysis -> alerts -> report")
    run_all_parser.add_argument("--analyze-limit", type=int, default=100)

    prep_demo_parser = subparsers.add_parser("prep-demo", help="Prepare deterministic demo readiness state")
    prep_demo_parser.add_argument("--batch-size", type=int, default=100)
    prep_demo_parser.add_argument("--max-batches", type=int, default=20)
    prep_demo_parser.add_argument("--clean-dead-letters", type=_str_to_bool, default=True)

    usage_parser = subparsers.add_parser("llm-usage", help="Summarize LLM token usage events")
    usage_parser.add_argument("--since-hours", type=int, default=None)
    usage_parser.add_argument("--path", type=str, default="artifacts/llm_usage.jsonl")

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


def cmd_report(week_start: str | None) -> None:
    week_start_dt = date.fromisoformat(week_start) if week_start else None
    stats = generate_weekly_report(week_start=week_start_dt)
    print(f"Report complete | html={stats.html_path} pdf={stats.pdf_path}")


def cmd_run_all(analyze_limit: int) -> None:
    print("Running ETL...")
    cmd_etl(since=None)
    print("Running analysis...")
    cmd_analyze(limit=analyze_limit)
    print("Running alerts...")
    cmd_alerts(now=None)
    print("Generating report...")
    cmd_report(week_start=None)


def cmd_prep_demo(batch_size: int, max_batches: int, clean_dead_letters: bool) -> None:
    stats = run_prep_demo(
        batch_size=batch_size,
        max_batches=max_batches,
        clean_dead_letters=clean_dead_letters,
    )
    print("Prep demo complete:")
    print(stats_to_json(stats))


def cmd_llm_usage(path: str, since_hours: int | None) -> None:
    summary = summarize_usage(path=path, since_hours=since_hours)
    print(json.dumps(summary, ensure_ascii=True, indent=2))


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

    if args.command == "report":
        cmd_report(week_start=args.week_start)
        return

    if args.command == "run-all":
        cmd_run_all(analyze_limit=args.analyze_limit)
        return

    if args.command == "prep-demo":
        cmd_prep_demo(
            batch_size=args.batch_size,
            max_batches=args.max_batches,
            clean_dead_letters=args.clean_dead_letters,
        )
        return

    if args.command == "llm-usage":
        cmd_llm_usage(path=args.path, since_hours=args.since_hours)
        return

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
