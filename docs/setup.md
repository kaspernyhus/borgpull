# SSH and borg serve setup

This guide walks through setting up the backup server (e.g. Proxmox) and remote host (e.g. Hetzner VPS) so borgpull can pull backups over an SSH reverse tunnel.

## Overview

borgpull SSHes from the backup server into the remote host, forwarding a Unix socket back (`-R`). On the remote side, borg uses `nc` to connect through that socket to `borg serve` running on the backup server. The repo lives on the backup server — data flows from remote to local through the tunnel.

## 1. Create a dedicated SSH key

On the **backup server**:

```sh
ssh-keygen -t ed25519 -f ~/.ssh/borgpull -C "borgpull"
```

## 2. Create a borg user on the remote host

On the **remote host**:

```sh
useradd -m -s /bin/bash borg
mkdir -p /home/borg/.ssh
chmod 700 /home/borg/.ssh
```

Copy the public key:

```sh
# on backup server
cat ~/.ssh/borgpull.pub
```

Paste it into `/home/borg/.ssh/authorized_keys` on the remote host:

```sh
echo "ssh-ed25519 AAAA... borgpull" > /home/borg/.ssh/authorized_keys
chmod 600 /home/borg/.ssh/authorized_keys
chown -R borg:borg /home/borg/.ssh
```

## 3. Allow the borg user to run borg with sudo

borgpull runs `sudo -E borg ...` on the remote host so borg can read files owned by other users (e.g. docker volumes). The `-E` flag preserves environment variables like `BORG_RSH`.

On the **remote host**, create `/etc/sudoers.d/borg`:

```
borg ALL=(ALL) NOPASSWD: /usr/bin/borg
```

If your hooks need sudo too (e.g. `sudo sqlite3 ...`), add those as well:

```
borg ALL=(ALL) NOPASSWD: /usr/bin/borg, /usr/bin/sqlite3
```

## 4. Configure SSH on the backup server

On the **backup server**, add to `~/.ssh/config`:

```
Host hetzner
    HostName <VPS-IP-or-hostname>
    User borg
    IdentityFile ~/.ssh/borgpull
    # allow the remote to forward the Unix socket
    StreamLocalBindUnlink yes
```

Verify connectivity:

```sh
ssh hetzner whoami
# should print: borg
```

## 5. Allow SSH to accept SendEnv

borgpull passes `BORG_RSH` and `BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK` via SSH's `SendEnv`. The remote sshd must be configured to accept them.

On the **remote host**, add to `/etc/ssh/sshd_config`:

```
AcceptEnv BORG_*
```

Then reload:

```sh
systemctl reload sshd
```

## 6. Set up borg serve on the backup server

`borg serve` runs on the backup server and listens on a Unix socket. When borgpull opens the SSH reverse tunnel, the remote borg connects back to this socket.

Create the repo directory:

```sh
mkdir -p /path/to/backups/my-vps
```

### Option A: systemd socket activation (recommended)

`/etc/systemd/system/borg-serve@.socket`:

```ini
[Unit]
Description=Borg serve socket for %i

[Socket]
ListenStream=/run/borg/%i.sock
Accept=true

[Install]
WantedBy=sockets.target
```

`/etc/systemd/system/borg-serve@@.service`:

```ini
[Unit]
Description=Borg serve for %i
After=network-online.target
Requires=borg-serve@%i.socket

[Service]
Type=simple
ExecStart=/usr/bin/borg serve --restrict-to-repository /path/to/backups/%i
StandardInput=socket
StandardOutput=socket
StandardError=journal
```

Enable:

```sh
systemctl daemon-reload
systemctl enable --now borg-serve@my-vps.socket
```

This creates `/run/borg/my-vps.sock`. Set `socket_path = "/run/borg/my-vps.sock"` in your borgpull config.

## 7. Initialize the repo

With everything wired up, initialize the borg repo from the backup server using borgpull:

```sh
borgpull init -c /etc/borgpull/config.toml
```

## 8. Test

```sh
# dry-run to verify command construction
borgpull -n -v

# real run
borgpull create -v
```
