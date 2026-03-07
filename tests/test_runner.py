import pytest

from borgpull.config import BorgConfig, Config, SshConfig, SourcesConfig
from borgpull.runner import build_borg_env, build_remote_command, build_ssh_command


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


class TestBuildRemoteCommand:
    def test_wraps_with_sudo(self):
        result = build_remote_command(["create", "--stats", "/repo::archive", "/data"])
        assert result == "sudo -E borg create --stats /repo::archive /data"

    def test_escapes_special_characters(self):
        result = build_remote_command(["create", "path with spaces"])
        assert result == "sudo -E borg create 'path with spaces'"
