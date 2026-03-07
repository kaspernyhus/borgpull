# borgpull

Pull-mode [BorgBackup](https://www.borgbackup.org/) orchestrator over SSH reverse tunnels.

borgmatic assumes borg runs locally. borgpull flips that — it SSHes into a remote host, sets up a reverse Unix-socket tunnel back to a local `borg serve`, and runs `borg create` remotely. This makes it ideal for pull-mode backups where a backup server (e.g. Proxmox) pulls from a remote VPS.

## How it works

```
borgpull (backup server)        Remote host (e.g. Hetzner VPS)
────────────────────            ──────────────────────────────
borgpull CLI                    sudo -E borg create ...
  └─ SSH -R sock:sock ──────►    └─ BORG_RSH="sh -c 'exec nc -U <sock>'"
       └─ borg serve                   (reverse tunnel back to local repo)
            └─ /vps-backups/
```

For each command, borgpull:

1. Opens an SSH connection with `-R <socket>:<socket>` to forward a Unix socket back to the local `borg serve`
2. Sets `BORG_RSH="sh -c 'exec nc -U <socket>'"` so borg on the remote side connects through the tunnel
3. Runs `sudo -E borg <subcommand>` on the remote host

## Prerequisites

- Python 3.11+
- `borg serve` running locally via systemd socket activation (or equivalent), listening on the configured Unix socket
- SSH access to the remote host
- `borg` and `nc` (netcat) installed on the remote host

## Installation

```sh
# with pipx (recommended on Debian/Ubuntu)
pipx install .

# or with pip in a venv
pip install .
```

## Configuration

Copy the example and edit it:

```sh
cp borgpull.example.toml borgpull.toml
```

borgpull searches for config in this order:

1. `--config` / `-c` flag
2. `./borgpull.toml`
3. `~/.config/borgpull/config.toml`
4. `/etc/borgpull/config.toml`

### Config reference

```toml
[ssh]
host = "hetzner"                    # required — SSH alias or IP
user = "root"                       # default: "root"
identity_file = "~/.ssh/borgmatic"  # optional
port = 22                           # optional

[borg]
repo = "ssh://borgbackup/vps-backups/myapp"  # required
socket_path = "/run/borg/hetzner.sock"       # required
encryption = "none"                 # default: "none" (only used by init)
compression = "lz4"                 # default: "lz4"

[sources]
paths = [                           # required
    "/data/app",
    "/tmp/backup.sqlite3",
]

[hooks]
before_create = [                   # optional — run on remote before borg create
    "sudo sqlite3 /data/app.db '.backup /tmp/backup.sqlite3'",
]
after_create = [                    # optional — run on remote after borg create
    "sudo rm -f /tmp/backup.sqlite3",
]

[retention]
keep_daily = 7                      # all optional
keep_weekly = 4
keep_monthly = 6
keep_yearly = 0

[checks]
enabled = ["repository"]            # default: ["repository"]
```

## Usage

```sh
# full cycle: hooks + create + prune + check
borgpull

# individual commands
borgpull create
borgpull prune
borgpull check
borgpull list
borgpull info
borgpull init

# flags
borgpull -n              # dry-run — print commands without executing
borgpull -v              # verbose — debug-level logging
borgpull -c /path.toml   # explicit config path
```

### Error handling

When running the full cycle (`borgpull` with no subcommand):

- **before_create hook fails** — abort entirely
- **borg create fails** — abort, skip after_create hooks
- **after_create hook fails** — log warning, continue to prune
- **prune fails** — log error, continue to check
- **check fails** — log error

## Development

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest

pytest
```
