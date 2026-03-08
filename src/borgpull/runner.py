from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys

from borgpull.config import Config

log = logging.getLogger("borgpull")


class RunError(Exception):
    pass


def build_borg_env(config: Config) -> dict[str, str]:
    sock = config.borg.socket_path
    return {
        "BORG_RSH": f"sh -c 'exec nc -U {sock}'",
        "BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK": "yes",
    }


def build_ssh_command(config: Config) -> list[str]:
    ssh = config.ssh
    sock = config.borg.socket_path

    cmd = ["ssh"]
    cmd += ["-R", f"{sock}:{sock}"]

    if ssh.identity_file:
        cmd += ["-i", ssh.identity_file]
    if ssh.port != 22:
        cmd += ["-p", str(ssh.port)]

    cmd += ["-o", "StreamLocalBindUnlink=yes"]

    for key in build_borg_env(config):
        cmd += ["-o", f"SendEnv={key}"]

    cmd.append(f"{ssh.user}@{ssh.host}")
    return cmd


def build_remote_command(borg_args: list[str]) -> str:
    escaped = " ".join(shlex.quote(a) for a in borg_args)
    return f"sudo -E borg {escaped}"


def run_borg(
    config: Config,
    borg_args: list[str],
    *,
    dry_run: bool = False,
) -> subprocess.CompletedProcess:
    remote_cmd = build_remote_command(borg_args)
    ssh_cmd = build_ssh_command(config)
    full_cmd = ssh_cmd + [remote_cmd]

    env = build_borg_env(config)

    if dry_run:
        log.info("dry-run: %s", " ".join(shlex.quote(c) for c in full_cmd))
        log.info("dry-run env: %s", env)
        return subprocess.CompletedProcess(full_cmd, 0)

    log.debug("running: %s", " ".join(shlex.quote(c) for c in full_cmd))
    log.debug("env: %s", env)

    result = subprocess.run(
        full_cmd,
        env={**os.environ, **env},
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    if result.returncode == 1:
        log.warning("borg %s completed with warnings (exit code 1)", borg_args[0])
    elif result.returncode > 1:
        raise RunError(f"borg {borg_args[0]} failed (exit code {result.returncode})")
    return result


def run_local(command: str, *, dry_run: bool = False) -> None:
    if dry_run:
        log.info("dry-run notification: %s", command)
        return

    log.info("notification: %s", command)
    result = subprocess.run(command, shell=True)
    if result.returncode != 0:
        raise RunError(f"notification command failed (exit code {result.returncode}): {command}")


def run_hook(config: Config, command: str, *, dry_run: bool = False) -> None:
    ssh_cmd = build_ssh_command(config)
    full_cmd = ssh_cmd + [command]

    if dry_run:
        log.info("dry-run hook: %s", " ".join(shlex.quote(c) for c in full_cmd))
        return

    log.info("hook: %s", command)
    result = subprocess.run(
        full_cmd,
        env={**os.environ, **build_borg_env(config)},
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    if result.returncode != 0:
        raise RunError(f"hook failed (exit code {result.returncode}): {command}")
