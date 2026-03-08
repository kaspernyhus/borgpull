from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(Exception):
    pass


@dataclass
class SshConfig:
    host: str
    user: str = "root"
    identity_file: str | None = None
    port: int = 22


@dataclass
class BorgConfig:
    repo: str
    socket_path: str
    encryption: str = "none"
    compression: str = "lz4"
    archive_name_format: str = "{hostname}-{now:%Y-%m-%dT%H:%M:%S}"


@dataclass
class SourcesConfig:
    paths: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)


@dataclass
class HooksConfig:
    before_create: list[str] = field(default_factory=list)
    after_create: list[str] = field(default_factory=list)


@dataclass
class RetentionConfig:
    keep_daily: int | None = None
    keep_weekly: int | None = None
    keep_monthly: int | None = None
    keep_yearly: int | None = None


@dataclass
class ChecksConfig:
    enabled: list[str] = field(default_factory=lambda: ["repository"])


@dataclass
class NotificationsConfig:
    on_success: list[str] = field(default_factory=list)
    on_failure: list[str] = field(default_factory=list)


@dataclass
class Config:
    ssh: SshConfig
    borg: BorgConfig
    sources: SourcesConfig
    hooks: HooksConfig = field(default_factory=HooksConfig)
    retention: RetentionConfig = field(default_factory=RetentionConfig)
    checks: ChecksConfig = field(default_factory=ChecksConfig)
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)


CONFIG_SEARCH_PATHS = [
    Path("borgpull.toml"),
    Path.home() / ".config" / "borgpull" / "config.toml",
    Path("/etc/borgpull/config.toml"),
]


def find_config() -> Path:
    for path in CONFIG_SEARCH_PATHS:
        if path.exists():
            return path
    raise ConfigError(
        "No config file found. Searched:\n"
        + "\n".join(f"  - {p}" for p in CONFIG_SEARCH_PATHS)
    )


def _apply_constants(data: dict, constants: dict[str, str]) -> dict:
    if not constants:
        return data

    def _substitute(value):
        if isinstance(value, str):
            for key, replacement in constants.items():
                value = value.replace(f"{{{key}}}", replacement)
            return value
        if isinstance(value, list):
            return [_substitute(item) for item in value]
        if isinstance(value, dict):
            return {k: _substitute(v) for k, v in value.items()}
        return value

    return _substitute(data)


def _require(data: dict, key: str, section: str) -> object:
    if key not in data:
        raise ConfigError(f"Missing required field '{key}' in [{section}]")
    return data[key]


def _parse_ssh(data: dict) -> SshConfig:
    section = data.get("ssh")
    if section is None:
        raise ConfigError("Missing required [ssh] section")
    return SshConfig(
        host=_require(section, "host", "ssh"),
        user=section.get("user", "root"),
        identity_file=section.get("identity_file"),
        port=section.get("port", 22),
    )


def _parse_borg(data: dict) -> BorgConfig:
    section = data.get("borg")
    if section is None:
        raise ConfigError("Missing required [borg] section")
    return BorgConfig(
        repo=_require(section, "repo", "borg"),
        socket_path=_require(section, "socket_path", "borg"),
        encryption=section.get("encryption", "none"),
        compression=section.get("compression", "lz4"),
        archive_name_format=section.get("archive_name_format", "{hostname}-{now:%Y-%m-%dT%H:%M:%S}"),
    )


def _parse_sources(data: dict) -> SourcesConfig:
    section = data.get("sources")
    if section is None:
        raise ConfigError("Missing required [sources] section")
    paths = _require(section, "paths", "sources")
    if not isinstance(paths, list) or not paths:
        raise ConfigError("[sources] paths must be a non-empty list")
    return SourcesConfig(paths=paths, exclude=section.get("exclude", []))


def _parse_hooks(data: dict) -> HooksConfig:
    section = data.get("hooks", {})
    return HooksConfig(
        before_create=section.get("before_create", []),
        after_create=section.get("after_create", []),
    )


def _parse_retention(data: dict) -> RetentionConfig:
    section = data.get("retention", {})
    return RetentionConfig(
        keep_daily=section.get("keep_daily"),
        keep_weekly=section.get("keep_weekly"),
        keep_monthly=section.get("keep_monthly"),
        keep_yearly=section.get("keep_yearly"),
    )


def _parse_checks(data: dict) -> ChecksConfig:
    section = data.get("checks", {})
    return ChecksConfig(
        enabled=section.get("enabled", ["repository"]),
    )


def _parse_notifications(data: dict) -> NotificationsConfig:
    section = data.get("notifications", {})
    return NotificationsConfig(
        on_success=section.get("on_success", []),
        on_failure=section.get("on_failure", []),
    )


def load_config(path: Path | None = None) -> Config:
    config_path = Path(path) if path else find_config()
    try:
        raw = config_path.read_text()
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{config_path}: {e}") from None

    constants = data.pop("constants", {})
    if constants:
        for key, value in constants.items():
            if not isinstance(value, str):
                raise ConfigError(f"{config_path}: [constants] values must be strings, got {type(value).__name__} for '{key}'")
        data = _apply_constants(data, constants)

    try:
        return Config(
            ssh=_parse_ssh(data),
            borg=_parse_borg(data),
            sources=_parse_sources(data),
            hooks=_parse_hooks(data),
            retention=_parse_retention(data),
            checks=_parse_checks(data),
            notifications=_parse_notifications(data),
        )
    except ConfigError as e:
        raise ConfigError(f"{config_path}: {e}") from None
