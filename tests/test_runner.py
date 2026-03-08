from unittest.mock import patch

import pytest

from borgpull.config import BorgConfig, Config, SshConfig, SourcesConfig
from borgpull.runner import RunError, build_borg_env, build_remote_command, build_ssh_command, run_borg, run_local


@pytest.fixture()
def config():
    return Config(
        ssh=SshConfig(host="hetzner", user="borg", identity_file="~/.ssh/borgmatic", port=2222),
        borg=BorgConfig(repo="ssh://borgbackup/vps-backups/myapp", socket_path="/run/borg/hetzner.sock"),
        sources=SourcesConfig(paths=["/data/app"]),
    )


@pytest.fixture()
def minimal_config():
    return Config(
        ssh=SshConfig(host="hetzner"),
        borg=BorgConfig(repo="ssh://borgbackup/vps-backups/myapp", socket_path="/run/borg/hetzner.sock"),
        sources=SourcesConfig(paths=["/data/app"]),
    )


class TestBuildBorgEnv:
    def test_sets_borg_rsh_with_socket(self, config):
        env = build_borg_env(config)
        assert env["BORG_RSH"] == "sh -c 'exec nc -U /run/borg/hetzner.sock'"

    def test_sets_unencrypted_access(self, config):
        env = build_borg_env(config)
        assert env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] == "yes"


class TestBuildSshCommand:
    def test_includes_reverse_tunnel(self, config):
        cmd = build_ssh_command(config)
        idx = cmd.index("-R")
        assert cmd[idx + 1] == "/run/borg/hetzner.sock:/run/borg/hetzner.sock"

    def test_includes_identity_file(self, config):
        cmd = build_ssh_command(config)
        idx = cmd.index("-i")
        assert cmd[idx + 1] == "~/.ssh/borgmatic"

    def test_includes_custom_port(self, config):
        cmd = build_ssh_command(config)
        idx = cmd.index("-p")
        assert cmd[idx + 1] == "2222"

    def test_omits_identity_and_port_for_defaults(self, minimal_config):
        cmd = build_ssh_command(minimal_config)
        assert "-i" not in cmd
        assert "-p" not in cmd

    def test_includes_sendenv_for_borg_vars(self, config):
        cmd = build_ssh_command(config)
        sendenv_values = [cmd[i + 1] for i, v in enumerate(cmd) if v == "-o" and cmd[i + 1].startswith("SendEnv=")]
        assert "SendEnv=BORG_RSH" in sendenv_values
        assert "SendEnv=BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK" in sendenv_values

    def test_ends_with_user_at_host(self, config):
        cmd = build_ssh_command(config)
        assert cmd[-1] == "borg@hetzner"

    def test_includes_stream_local_bind_unlink(self, config):
        cmd = build_ssh_command(config)
        idx = cmd.index("StreamLocalBindUnlink=yes") - 1
        assert cmd[idx] == "-o"


class TestRunBorg:
    @patch("borgpull.runner.subprocess.run")
    def test_exit_code_1_logs_warning_and_does_not_raise(self, mock_run, config, caplog):
        import logging
        mock_run.return_value.returncode = 1
        with caplog.at_level(logging.WARNING, logger="borgpull"):
            run_borg(config, ["create", "repo::archive"])
        assert "warnings" in caplog.text

    @patch("borgpull.runner.subprocess.run")
    def test_exit_code_2_raises(self, mock_run, config):
        mock_run.return_value.returncode = 2
        with pytest.raises(RunError, match="failed \\(exit code 2\\)"):
            run_borg(config, ["create", "repo::archive"])

    @patch("borgpull.runner.subprocess.run")
    def test_exit_code_0_succeeds(self, mock_run, config):
        mock_run.return_value.returncode = 0
        run_borg(config, ["create", "repo::archive"])  # no exception


class TestRunLocal:
    def test_dry_run_logs_without_executing(self, caplog):
        import logging
        with caplog.at_level(logging.INFO, logger="borgpull"):
            run_local("echo hello", dry_run=True)
        assert "dry-run" in caplog.text
        assert "echo hello" in caplog.text

    @patch("borgpull.runner.subprocess.run")
    def test_success_does_not_raise(self, mock_run):
        mock_run.return_value.returncode = 0
        run_local("echo hello")

    @patch("borgpull.runner.subprocess.run")
    def test_nonzero_exit_raises_run_error(self, mock_run):
        mock_run.return_value.returncode = 1
        with pytest.raises(RunError, match="exit code 1"):
            run_local("false")

    @patch("borgpull.runner.subprocess.run")
    def test_runs_with_shell_true(self, mock_run):
        mock_run.return_value.returncode = 0
        run_local("echo hello")
        mock_run.assert_called_once_with("echo hello", shell=True)


class TestBuildRemoteCommand:
    def test_wraps_with_sudo(self):
        result = build_remote_command(["create", "--stats", "/repo::archive", "/data"])
        assert result == "sudo -E borg create --stats /repo::archive /data"

    def test_escapes_special_characters(self):
        result = build_remote_command(["create", "path with spaces"])
        assert result == "sudo -E borg create 'path with spaces'"
