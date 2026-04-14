from __future__ import annotations

import argparse
import json

from src.alerts.detector import run_alert_detection
from src.analysis.llm_analyzer import analyze_pending_reviews
from src.analysis.usage_tracker import summarize_usage
from src.core.db import session_scope
from src.etl.pipeline import run_etl
from src.reports.weekly_report import generate_weekly_report
from src.scripts.prep_demo import run_prep_demo, stats_to_json
from src.scripts.seed import seed_customer_surveys
from src.cli.utils import parse_optional_date, parse_optional_datetime


def _print_errors(errors: list[str]) -> None:
    if not errors:
        return
    print("Errors:")
    for err in errors:
        print(f"- {err}")


def handle_seed(args: argparse.Namespace) -> None:
    with session_scope() as session:
        stats = seed_customer_surveys(session=session, total=args.total)
    print(f"Seed complete. Inserted surveys: {stats.inserted}")


def handle_etl(args: argparse.Namespace) -> None:
    since_dt = parse_optional_datetime(args.since)
    stats = run_etl(since=since_dt)
    print(
        "ETL complete | "
        f"api={stats.api_extracted} survey={stats.survey_extracted} "
        f"transformed={stats.transformed} loaded={stats.loaded} dead_letters={stats.dead_letters}"
    )
    _print_errors(stats.errors)


def handle_analyze(args: argparse.Namespace) -> None:
    stats = analyze_pending_reviews(limit=args.limit)
    print(
        "Analysis complete | "
        f"pending={stats.pending} analyzed={stats.analyzed} stored={stats.stored} dead_letters={stats.dead_letters}"
    )
    _print_errors(stats.errors)


def handle_alerts(args: argparse.Namespace) -> None:
    now_dt = parse_optional_datetime(args.now)
    stats = run_alert_detection(now=now_dt)
    print(
        "Alerts complete | "
        f"generated={stats.generated} persisted={stats.persisted} notified={stats.notified}"
    )


def handle_report(args: argparse.Namespace) -> None:
    week_start_dt = parse_optional_date(args.week_start)
    stats = generate_weekly_report(week_start=week_start_dt)
    print(f"Report complete | html={stats.html_path} pdf={stats.pdf_path}")


def handle_run_all(args: argparse.Namespace) -> None:
    print("Running ETL...")
    handle_etl(argparse.Namespace(since=None))
    print("Running analysis...")
    handle_analyze(argparse.Namespace(limit=args.analyze_limit))
    print("Running alerts...")
    handle_alerts(argparse.Namespace(now=None))
    print("Generating report...")
    handle_report(argparse.Namespace(week_start=None))


def handle_prep_demo(args: argparse.Namespace) -> None:
    stats = run_prep_demo(
        batch_size=args.batch_size,
        max_batches=args.max_batches,
        clean_dead_letters=args.clean_dead_letters,
    )
    print("Prep demo complete:")
    print(stats_to_json(stats))


def handle_llm_usage(args: argparse.Namespace) -> None:
    summary = summarize_usage(path=args.path, since_hours=args.since_hours)
    print(json.dumps(summary, ensure_ascii=True, indent=2))

