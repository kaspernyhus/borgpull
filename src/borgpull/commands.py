from __future__ import annotations

import logging
import subprocess
from datetime import datetime

from borgpull.config import Config
from borgpull.runner import run_borg, run_hook

log = logging.getLogger("borgpull")


def _archive_name(config: Config) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    return f"{config.borg.repo}::{timestamp}"


def _retention_args(config: Config) -> list[str]:
    args: list[str] = []
    r = config.retention
    if r.keep_daily is not None:
        args += ["--keep-daily", str(r.keep_daily)]
    if r.keep_weekly is not None:
        args += ["--keep-weekly", str(r.keep_weekly)]
    if r.keep_monthly is not None:
        args += ["--keep-monthly", str(r.keep_monthly)]
    if r.keep_yearly is not None:
        args += ["--keep-yearly", str(r.keep_yearly)]
    return args


def create(config: Config, *, dry_run: bool = False) -> None:
    for hook in config.hooks.before_create:
        run_hook(config, hook, dry_run=dry_run)

    args = [
        "create",
        "--stats",
        "--compression", config.borg.compression,
        _archive_name(config),
        *config.sources.paths,
    ]
    run_borg(config, args, dry_run=dry_run)

    for hook in config.hooks.after_create:
        try:
            run_hook(config, hook, dry_run=dry_run)
        except subprocess.CalledProcessError:
            log.warning("after_create hook failed: %s", hook)


def prune(config: Config, *, dry_run: bool = False) -> None:
    retention = _retention_args(config)
    if not retention:
        log.info("no retention policy configured, skipping prune")
        return

    args = ["prune", "--stats", "--list", *retention, config.borg.repo]
    run_borg(config, args, dry_run=dry_run)


def check(config: Config, *, dry_run: bool = False) -> None:
    for check_type in config.checks.enabled:
        args = ["check", f"--{check_type}-only", config.borg.repo]
        run_borg(config, args, dry_run=dry_run)


def list_archives(config: Config, *, dry_run: bool = False) -> None:
    run_borg(config, ["list", config.borg.repo], dry_run=dry_run)


def info(config: Config, *, dry_run: bool = False) -> None:
    run_borg(config, ["info", config.borg.repo], dry_run=dry_run)


def init(config: Config, *, dry_run: bool = False) -> None:
    args = ["init", "--encryption", config.borg.encryption, config.borg.repo]
    run_borg(config, args, dry_run=dry_run)


def run_all(config: Config, *, dry_run: bool = False) -> None:
    create(config, dry_run=dry_run)

    try:
        prune(config, dry_run=dry_run)
    except Exception:
        log.error("prune failed, continuing to check")

    try:
        check(config, dry_run=dry_run)
    except Exception:
        log.error("check failed")
