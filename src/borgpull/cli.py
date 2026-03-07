from __future__ import annotations

import argparse
import logging
import sys

from borgpull import __version__
from borgpull.commands import check, create, info, init, list_archives, prune, run_all
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
    sub.add_parser("check", help="borg check")
    sub.add_parser("list", help="borg list")
    sub.add_parser("info", help="borg info")
    sub.add_parser("init", help="borg init")

    return parser


COMMANDS = {
    "create": lambda cfg, dr: create(cfg, dry_run=dr),
    "prune": lambda cfg, dr: prune(cfg, dry_run=dr),
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

    try:
        if args.command is None:
            run_all(config, dry_run=args.dry_run)
        else:
            COMMANDS[args.command](config, args.dry_run)
    except Exception as e:
        log.error("%s", e)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
