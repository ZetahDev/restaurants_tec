from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FeedbackIQ CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("etl", "analyze", "alerts", "report", "run-all", "seed"):
        subparsers.add_parser(command)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    print(f"Command '{args.command}' is scaffolded and will be implemented in next commits.")


if __name__ == "__main__":
    main()
