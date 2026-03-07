from unittest.mock import call, patch

import pytest

from borgpull.config import (
    BorgConfig,
    ChecksConfig,
    Config,
    HooksConfig,
    RetentionConfig,
    SourcesConfig,
    SshConfig,
)
from borgpull.commands import create, prune, check, init, run_all


@pytest.fixture()
def config():
    return Config(
        ssh=SshConfig(host="hetzner"),
        borg=BorgConfig(
            repo="ssh://borgbackup/vps-backups/myapp",
            socket_path="/run/borg/hetzner.sock",
            compression="lz4",
            encryption="none",
        ),
        sources=SourcesConfig(paths=["/data/app", "/data/db"]),
        hooks=HooksConfig(
            before_create=["echo before"],
            after_create=["echo after"],
        ),
        retention=RetentionConfig(keep_daily=7, keep_weekly=4),
        checks=ChecksConfig(enabled=["repository", "archives"]),
    )


@pytest.fixture()
def config_no_retention(config):
    config.retention = RetentionConfig()
    return config


class TestCreate:
    @patch("borgpull.commands.run_borg")
    @patch("borgpull.commands.run_hook")
    def test_runs_hooks_and_borg(self, mock_hook, mock_borg, config):
        create(config, dry_run=True)

        assert mock_hook.call_args_list[0] == call(config, "echo before", dry_run=True)
        assert mock_hook.call_args_list[1] == call(config, "echo after", dry_run=True)

        borg_args = mock_borg.call_args[0][1]
        assert borg_args[0] == "create"
        assert "--stats" in borg_args
        assert "--compression" in borg_args
        assert "lz4" in borg_args
        assert "/data/app" in borg_args
        assert "/data/db" in borg_args

    @patch("borgpull.commands.run_borg", side_effect=Exception("borg failed"))
    @patch("borgpull.commands.run_hook")
    def test_skips_after_hooks_on_borg_failure(self, mock_hook, mock_borg, config):
        with pytest.raises(Exception, match="borg failed"):
            create(config, dry_run=False)
        assert mock_hook.call_count == 1  # only before_create


class TestPrune:
    @patch("borgpull.commands.run_borg")
    def test_builds_retention_args(self, mock_borg, config):
        prune(config, dry_run=True)
        borg_args = mock_borg.call_args[0][1]
        assert borg_args == [
            "prune", "--stats", "--list",
            "--keep-daily", "7",
            "--keep-weekly", "4",
            config.borg.repo,
        ]

    @patch("borgpull.commands.run_borg")
    def test_skips_when_no_retention(self, mock_borg, config_no_retention):
        prune(config_no_retention, dry_run=True)
        mock_borg.assert_not_called()


class TestCheck:
    @patch("borgpull.commands.run_borg")
    def test_runs_each_check_type(self, mock_borg, config):
        check(config, dry_run=True)
        assert mock_borg.call_count == 2
        assert mock_borg.call_args_list[0][0][1] == ["check", "--repository-only", config.borg.repo]
        assert mock_borg.call_args_list[1][0][1] == ["check", "--archives-only", config.borg.repo]


class TestInit:
    @patch("borgpull.commands.run_borg")
    def test_passes_encryption(self, mock_borg, config):
        init(config, dry_run=True)
        borg_args = mock_borg.call_args[0][1]
        assert borg_args == ["init", "--encryption", "none", config.borg.repo]


class TestRunAll:
    @patch("borgpull.commands.check")
    @patch("borgpull.commands.prune")
    @patch("borgpull.commands.create")
    def test_calls_create_prune_check(self, mock_create, mock_prune, mock_check, config):
        run_all(config, dry_run=True)
        mock_create.assert_called_once_with(config, dry_run=True)
        mock_prune.assert_called_once_with(config, dry_run=True)
        mock_check.assert_called_once_with(config, dry_run=True)

    @patch("borgpull.commands.check")
    @patch("borgpull.commands.prune", side_effect=Exception("prune failed"))
    @patch("borgpull.commands.create")
    def test_continues_to_check_if_prune_fails(self, mock_create, mock_prune, mock_check, config):
        run_all(config, dry_run=True)
        mock_check.assert_called_once()
