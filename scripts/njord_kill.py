from __future__ import annotations

import argparse
import asyncio
from typing import cast

from core.config import Config, load_config
from core.kill_switch import clear_file, file_tripped, redis_tripped, trip_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Njord kill-switch helper")
    parser.add_argument(
        "--config-root",
        default=".",
        help="Directory containing config/ (defaults to current working directory)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("trip-file", "clear-file", "check"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--path", help="Override kill switch file path")
    return parser


def _resolve_path(args: argparse.Namespace, cfg: Config) -> str:
    path_override = getattr(args, "path", None)
    if path_override is not None:
        return cast(str, path_override)
    return cfg.risk.kill_switch_file


async def _handle_check(args: argparse.Namespace, cfg: Config) -> int:
    path = _resolve_path(args, cfg)
    file_state = file_tripped(path)

    tripped = False
    redis_state: str
    try:
        redis_tripped_state = await redis_tripped(cfg.redis.url, cfg.risk.kill_switch_key)
    except Exception as exc:  # pragma: no cover - depends on redis availability
        redis_state = f"error({exc})"
    else:
        tripped = redis_tripped_state
        redis_state = "tripped" if redis_tripped_state else "clear"

    overall = "TRIPPED" if file_state or tripped else "CLEAR"
    print(f"{overall} file={'tripped' if file_state else 'clear'} redis={redis_state}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = load_config(args.config_root)
    path = _resolve_path(args, cfg)

    if args.command == "trip-file":
        trip_file(path)
        print(f"TRIPPED file={path}")
        return 0
    if args.command == "clear-file":
        clear_file(path)
        print(f"CLEARED file={path}")
        return 0
    if args.command == "check":
        return asyncio.run(_handle_check(args, cfg))

    parser.error(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
