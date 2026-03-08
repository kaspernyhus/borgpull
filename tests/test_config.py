import pytest

from borgpull.config import ConfigError, load_config

MINIMAL_CONFIG = """\
[ssh]
host = "hetzner"

[borg]
repo = "ssh://borgbackup/vps-backups/myapp"
socket_path = "/run/borg/hetzner.sock"

[sources]
paths = ["/data/app"]
"""

FULL_CONFIG = """\
[ssh]
host = "hetzner"
user = "borg"
identity_file = "~/.ssh/borgmatic"
port = 2222

[borg]
repo = "ssh://borgbackup/vps-backups/myapp"
socket_path = "/run/borg/hetzner.sock"
encryption = "repokey"
compression = "zstd,3"

[sources]
paths = ["/data/app", "/data/db"]

[hooks]
before_create = ["sudo sqlite3 /data/db.sqlite '.backup /tmp/db.sqlite'"]
after_create = ["sudo rm -f /tmp/db.sqlite"]

[retention]
keep_daily = 7
keep_weekly = 4
keep_monthly = 6

[checks]
enabled = ["repository", "archives"]
"""


@pytest.fixture()
def minimal_config(tmp_path):
    path = tmp_path / "borgpull.toml"
    path.write_text(MINIMAL_CONFIG)
    return path


@pytest.fixture()
def full_config(tmp_path):
    path = tmp_path / "borgpull.toml"
    path.write_text(FULL_CONFIG)
    return path


class TestLoadConfigDefaults:
    def test_applies_ssh_defaults(self, minimal_config):
        cfg = load_config(minimal_config)
        assert cfg.ssh.host == "hetzner"
        assert cfg.ssh.user == "root"
        assert cfg.ssh.identity_file is None
        assert cfg.ssh.port == 22

    def test_applies_borg_defaults(self, minimal_config):
        cfg = load_config(minimal_config)
        assert cfg.borg.encryption == "none"
        assert cfg.borg.compression == "lz4"

    def test_applies_empty_hooks(self, minimal_config):
        cfg = load_config(minimal_config)
        assert cfg.hooks.before_create == []
        assert cfg.hooks.after_create == []

    def test_applies_default_checks(self, minimal_config):
        cfg = load_config(minimal_config)
        assert cfg.checks.enabled == ["repository"]

    def test_applies_no_retention(self, minimal_config):
        cfg = load_config(minimal_config)
        assert cfg.retention.keep_daily is None


class TestLoadConfigFull:
    def test_parses_all_sections(self, full_config):
        cfg = load_config(full_config)

        assert cfg.ssh == pytest.approx(cfg.ssh)  # just checking it loaded
        assert cfg.ssh.user == "borg"
        assert cfg.ssh.port == 2222
        assert cfg.ssh.identity_file == "~/.ssh/borgmatic"

        assert cfg.borg.encryption == "repokey"
        assert cfg.borg.compression == "zstd,3"

        assert cfg.sources.paths == ["/data/app", "/data/db"]

        assert len(cfg.hooks.before_create) == 1
        assert len(cfg.hooks.after_create) == 1

        assert cfg.retention.keep_daily == 7
        assert cfg.retention.keep_weekly == 4
        assert cfg.retention.keep_monthly == 6
        assert cfg.retention.keep_yearly is None

        assert cfg.checks.enabled == ["repository", "archives"]


class TestLoadConfigErrors:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "nonexistent.toml")

    @pytest.mark.parametrize(
        "toml_content, expected_error",
        [
            pytest.param(
                "[borg]\nrepo = 'x'\nsocket_path = 'y'\n[sources]\npaths = ['/a']",
                "Missing required \\[ssh\\] section",
                id="missing_ssh",
            ),
            pytest.param(
                "[ssh]\nhost = 'h'\n[sources]\npaths = ['/a']",
                "Missing required \\[borg\\] section",
                id="missing_borg",
            ),
            pytest.param(
                "[ssh]\nhost = 'h'\n[borg]\nrepo = 'x'\nsocket_path = 'y'",
                "Missing required \\[sources\\] section",
                id="missing_sources",
            ),
            pytest.param(
                "[ssh]\nhost = 'h'\n[borg]\nrepo = 'x'\nsocket_path = 'y'\n[sources]\npaths = []",
                "paths must be a non-empty list",
                id="empty_paths",
            ),
            pytest.param(
                "[ssh]\n[borg]\nrepo = 'x'\nsocket_path = 'y'\n[sources]\npaths = ['/a']",
                "Missing required field 'host' in \\[ssh\\]",
                id="missing_ssh_host",
            ),
        ],
    )
    def test_missing_required_fields(self, tmp_path, toml_content, expected_error):
        path = tmp_path / "bad.toml"
        path.write_text(toml_content)
        with pytest.raises(ConfigError, match=expected_error):
            load_config(path)

    def test_invalid_toml_raises_with_file_path(self, tmp_path):
        path = tmp_path / "broken.toml"
        path.write_text("[ssh]\nhost = [")
        with pytest.raises(ConfigError, match="broken.toml"):
            load_config(path)

    def test_validation_error_includes_file_path(self, tmp_path):
        path = tmp_path / "myconfig.toml"
        path.write_text("[ssh]\nhost = 'h'\n[sources]\npaths = ['/a']")
        with pytest.raises(ConfigError, match="myconfig.toml.*Missing required \\[borg\\] section"):
            load_config(path)


CONSTANTS_CONFIG = """\
[constants]
upload = "/mnt/data/upload"
backup_path = "/mnt/backups"

[ssh]
host = "hetzner"

[borg]
repo = "{backup_path}/immich-borg"
socket_path = "/run/borg/hetzner.sock"

[sources]
paths = ["{upload}"]
exclude = ["{upload}/thumbs/", "{upload}/encoded-video/"]

[hooks]
before_create = ["echo backing up {upload}"]
"""


class TestConstants:
    def test_substitutes_in_all_string_values(self, tmp_path):
        path = tmp_path / "borgpull.toml"
        path.write_text(CONSTANTS_CONFIG)
        cfg = load_config(path)

        assert cfg.borg.repo == "/mnt/backups/immich-borg"
        assert cfg.sources.paths == ["/mnt/data/upload"]
        assert cfg.sources.exclude == ["/mnt/data/upload/thumbs/", "/mnt/data/upload/encoded-video/"]
        assert cfg.hooks.before_create == ["echo backing up /mnt/data/upload"]

    def test_leaves_non_constant_braces_alone(self, tmp_path):
        path = tmp_path / "borgpull.toml"
        path.write_text(CONSTANTS_CONFIG)
        cfg = load_config(path)
        assert "{hostname}" in cfg.borg.archive_name_format

    def test_no_constants_section_works(self, minimal_config):
        cfg = load_config(minimal_config)
        assert cfg.ssh.host == "hetzner"

    def test_non_string_constant_raises(self, tmp_path):
        path = tmp_path / "bad.toml"
        path.write_text(
            "[constants]\nfoo = 42\n"
            "[ssh]\nhost = 'h'\n[borg]\nrepo = 'x'\nsocket_path = 'y'\n"
            "[sources]\npaths = ['/a']"
        )
        with pytest.raises(ConfigError, match="must be strings"):
            load_config(path)


NOTIFICATIONS_CONFIG = """\
[ssh]
host = "hetzner"

[borg]
repo = "ssh://borgbackup/vps-backups/myapp"
socket_path = "/run/borg/hetzner.sock"

[sources]
paths = ["/data/app"]

[notifications]
on_success = ["curl -s -d 'backup OK' ntfy.sh/my-topic"]
on_failure = ["curl -s -d 'backup FAILED' ntfy.sh/my-topic"]
"""


class TestNotificationsConfig:
    def test_defaults_to_empty_lists(self, minimal_config):
        cfg = load_config(minimal_config)
        assert cfg.notifications.on_success == []
        assert cfg.notifications.on_failure == []

    def test_parses_on_success_and_on_failure(self, tmp_path):
        path = tmp_path / "borgpull.toml"
        path.write_text(NOTIFICATIONS_CONFIG)
        cfg = load_config(path)
        assert cfg.notifications.on_success == ["curl -s -d 'backup OK' ntfy.sh/my-topic"]
        assert cfg.notifications.on_failure == ["curl -s -d 'backup FAILED' ntfy.sh/my-topic"]
