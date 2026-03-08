from unittest.mock import patch

import pytest

from borgpull.cli import main


MINIMAL_CONFIG = """\
[ssh]
host = "hetzner"

[borg]
repo = "ssh://borgbackup/vps-backups/myapp"
socket_path = "/run/borg/hetzner.sock"

[sources]
paths = ["/data/app"]

[notifications]
on_success = ["curl -s -d 'backup OK' ntfy.sh/topic"]
on_failure = ["curl -s -d 'backup FAILED' ntfy.sh/topic"]
"""


@pytest.fixture()
def config_file(tmp_path):
    path = tmp_path / "borgpull.toml"
    path.write_text(MINIMAL_CONFIG)
    return path


class TestNotificationsOnSuccess:
    @patch("borgpull.cli.run_local")
    @patch("borgpull.cli.run_all")
    def test_on_success_called_after_successful_backup(self, mock_run_all, mock_run_local, config_file):
        mock_run_all.return_value = None
        exit_code = main(["-c", str(config_file)])
        assert exit_code == 0
        mock_run_local.assert_called_once_with("curl -s -d 'backup OK' ntfy.sh/topic", dry_run=False)

    @patch("borgpull.cli.run_local")
    @patch("borgpull.cli.run_all")
    def test_on_failure_not_called_on_success(self, mock_run_all, mock_run_local, config_file):
        mock_run_all.return_value = None
        main(["-c", str(config_file)])
        called_cmds = [c.args[0] for c in mock_run_local.call_args_list]
        assert not any("FAILED" in cmd for cmd in called_cmds)

    @patch("borgpull.cli.run_local")
    @patch("borgpull.cli.run_all")
    def test_notification_failure_does_not_change_exit_code(self, mock_run_all, mock_run_local, config_file):
        from borgpull.runner import RunError
        mock_run_all.return_value = None
        mock_run_local.side_effect = RunError("curl failed")
        exit_code = main(["-c", str(config_file)])
        assert exit_code == 0

    @patch("borgpull.cli.run_local")
    @patch("borgpull.cli.run_all")
    def test_dry_run_passes_flag_to_run_local(self, mock_run_all, mock_run_local, config_file):
        mock_run_all.return_value = None
        main(["-c", str(config_file), "-n"])
        mock_run_local.assert_called_once_with("curl -s -d 'backup OK' ntfy.sh/topic", dry_run=True)


class TestNotificationsOnFailure:
    @patch("borgpull.cli.run_local")
    @patch("borgpull.cli.run_all")
    def test_on_failure_called_after_failed_backup(self, mock_run_all, mock_run_local, config_file):
        mock_run_all.side_effect = Exception("borg create failed")
        exit_code = main(["-c", str(config_file)])
        assert exit_code == 1
        mock_run_local.assert_called_once_with("curl -s -d 'backup FAILED' ntfy.sh/topic", dry_run=False)

    @patch("borgpull.cli.run_local")
    @patch("borgpull.cli.run_all")
    def test_on_success_not_called_on_failure(self, mock_run_all, mock_run_local, config_file):
        mock_run_all.side_effect = Exception("borg create failed")
        main(["-c", str(config_file)])
        called_cmds = [c.args[0] for c in mock_run_local.call_args_list]
        assert not any("OK" in cmd for cmd in called_cmds)

    @patch("borgpull.cli.run_local")
    @patch("borgpull.cli.run_all")
    def test_notification_failure_preserves_failure_exit_code(self, mock_run_all, mock_run_local, config_file):
        from borgpull.runner import RunError
        mock_run_all.side_effect = Exception("borg create failed")
        mock_run_local.side_effect = RunError("curl failed")
        exit_code = main(["-c", str(config_file)])
        assert exit_code == 1


class TestNotificationsNotCalledForSubcommands:
    @patch("borgpull.cli.run_local")
    @patch("borgpull.cli.list_archives")
    def test_subcommand_does_not_trigger_notifications(self, mock_list, mock_run_local, config_file):
        mock_list.return_value = None
        main(["-c", str(config_file), "list"])
        mock_run_local.assert_not_called()
