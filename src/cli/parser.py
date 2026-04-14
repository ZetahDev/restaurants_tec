from __future__ import annotations

import argparse

from src.cli.commands import (
    handle_alerts,
    handle_analyze,
    handle_etl,
    handle_llm_usage,
    handle_prep_demo,
    handle_report,
    handle_run_all,
    handle_seed,
)
from src.cli.utils import parse_bool_arg


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FeedbackIQ CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed", help="Seed customer surveys table")
    seed_parser.add_argument("--total", type=int, default=220, help="Base generated surveys before forced cases")
    seed_parser.set_defaults(handler=handle_seed)

    etl_parser = subparsers.add_parser("etl", help="Run ETL pipeline")
    etl_parser.add_argument("--since", type=str, default=None, help="ISO-8601 UTC timestamp")
    etl_parser.set_defaults(handler=handle_etl)

    analyze_parser = subparsers.add_parser("analyze", help="Run LLM analysis for pending reviews")
    analyze_parser.add_argument("--limit", type=int, default=100)
    analyze_parser.set_defaults(handler=handle_analyze)

    alerts_parser = subparsers.add_parser("alerts", help="Run alert detection")
    alerts_parser.add_argument("--now", type=str, default=None, help="ISO-8601 UTC timestamp")
    alerts_parser.set_defaults(handler=handle_alerts)

    report_parser = subparsers.add_parser("report", help="Generate weekly report")
    report_parser.add_argument("--week-start", type=str, default=None, help="YYYY-MM-DD")
    report_parser.set_defaults(handler=handle_report)

    run_all_parser = subparsers.add_parser("run-all", help="Run ETL -> analysis -> alerts -> report")
    run_all_parser.add_argument("--analyze-limit", type=int, default=100)
    run_all_parser.set_defaults(handler=handle_run_all)

    prep_demo_parser = subparsers.add_parser("prep-demo", help="Prepare deterministic demo readiness state")
    prep_demo_parser.add_argument("--batch-size", type=int, default=100)
    prep_demo_parser.add_argument("--max-batches", type=int, default=20)
    prep_demo_parser.add_argument("--clean-dead-letters", type=parse_bool_arg, default=True)
    prep_demo_parser.set_defaults(handler=handle_prep_demo)

    usage_parser = subparsers.add_parser("llm-usage", help="Summarize LLM token usage events")
    usage_parser.add_argument("--since-hours", type=int, default=None)
    usage_parser.add_argument("--path", type=str, default="artifacts/llm_usage.jsonl")
    usage_parser.set_defaults(handler=handle_llm_usage)

    return parser

