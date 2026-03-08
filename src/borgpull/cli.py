from __future__ import annotations

import argparse
import logging
import sys
import time

from borgpull import __version__
from borgpull.commands import check, compact, create, info, init, list_archives, prune, run_all
from borgpull.config import ConfigError, load_config

log = logging.getLogger("borgpull")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("borgpull: %(message)s"))
    logging.getLogger("borgpull").setLevel(level)
    logging.getLogger("borgpull").addHandler(handler)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="borgpull",
        description="Pull-mode borg backup orchestrator",
    )
    parser.add_argument("--version", action="version", version=f"borgpull {__version__}")
    parser.add_argument("-c", "--config", help="path to config file")
    parser.add_argument("-v", "--verbose", action="store_true", help="enable debug output")
    parser.add_argument("-n", "--dry-run", action="store_true", help="show commands without executing")

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("create", help="run hooks + borg create")
    sub.add_parser("prune", help="borg prune")
    sub.add_parser("compact", help="borg compact")
    sub.add_parser("check", help="borg check")
    sub.add_parser("list", help="borg list")
    sub.add_parser("info", help="borg info")
    sub.add_parser("init", help="borg init")
    sub.add_parser("verify", help="validate config file")

    return parser


COMMANDS = {
    "create": lambda cfg, dr: create(cfg, dry_run=dr),
    "prune": lambda cfg, dr: prune(cfg, dry_run=dr),
    "compact": lambda cfg, dr: compact(cfg, dry_run=dr),
    "check": lambda cfg, dr: check(cfg, dry_run=dr),
    "list": lambda cfg, dr: list_archives(cfg, dry_run=dr),
    "info": lambda cfg, dr: info(cfg, dry_run=dr),
    "init": lambda cfg, dr: init(cfg, dry_run=dr),
}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    try:
        config = load_config(args.config)
    except ConfigError as e:
        log.error("%s", e)
        return 1

    if args.command == "verify":
        log.info("config OK")
        return 0

    is_backup = args.command is None
    if is_backup:
        log.info("starting backup")
        start = time.monotonic()

    try:
        if is_backup:
            run_all(config, dry_run=args.dry_run)
        else:
            COMMANDS[args.command](config, args.dry_run)
    except Exception as e:
        if is_backup:
            log.error("backup failed after %s: %s", _format_duration(time.monotonic() - start), e)
        else:
            log.error("%s", e)
        return 1

    if is_backup:
        log.info("backup finished in %s", _format_duration(time.monotonic() - start))
    return 0


def _format_duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


if __name__ == "__main__":
    sys.exit(main())
