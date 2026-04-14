from __future__ import annotations

from src.cli import build_parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    handler = getattr(args, "handler", None)

    if handler is None:
        parser.error(f"Unsupported command: {getattr(args, 'command', '<unknown>')}")
        return

    handler(args)


if __name__ == "__main__":
    main()
