from __future__ import annotations

import argparse

from src.core.db import session_scope
from src.scripts.seed import seed_customer_surveys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FeedbackIQ CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed", help="Seed customer surveys table")
    seed_parser.add_argument("--total", type=int, default=220, help="Base generated surveys before forced cases")

    for command in ("etl", "analyze", "alerts", "report", "run-all"):
        subparsers.add_parser(command)

    return parser


def cmd_seed(total: int) -> None:
    with session_scope() as session:
        stats = seed_customer_surveys(session=session, total=total)
    print(f"Seed complete. Inserted surveys: {stats.inserted}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "seed":
        cmd_seed(total=args.total)
        return

    print(f"Command '{args.command}' is scaffolded and will be implemented in next commits.")


if __name__ == "__main__":
    main()
