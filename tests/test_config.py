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
