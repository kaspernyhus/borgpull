# Scheduling with systemd

Run borgpull automatically on a timer.

## Service unit

`/etc/systemd/system/borgpull.service`:

```ini
[Unit]
Description=borgpull backup
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/root/.local/bin/borgpull -c /etc/borgpull/config.toml
```

Adjust the `ExecStart` path to wherever pipx installed the binary. You can find it with `pipx environment`.

## Timer unit

`/etc/systemd/system/borgpull.timer`:

```ini
[Unit]
Description=Run borgpull daily

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

- `OnCalendar=daily` — runs at midnight
- `RandomizedDelaySec=1h` — spreads the start time randomly within 1 hour to avoid thundering-herd across multiple hosts
- `Persistent=true` — if the server was off when the timer should have fired, it triggers on next boot

## Enable

```sh
systemctl daemon-reload
systemctl enable --now borgpull.timer
```

## Check status

```sh
# next scheduled run
systemctl list-timers borgpull.timer

# logs from last run
journalctl -u borgpull.service -e
```

## Multiple configs

If you back up multiple remote hosts, create one service/timer pair per host:

`/etc/systemd/system/borgpull@.service`:

```ini
[Unit]
Description=borgpull backup for %i
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/root/.local/bin/borgpull -c /etc/borgpull/%i.toml
```

`/etc/systemd/system/borgpull@.timer`:

```ini
[Unit]
Description=Run borgpull daily for %i

[Timer]
OnCalendar=*-*-* 03:00:00
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

Then enable per host:

```sh
systemctl enable --now borgpull@hetzner.timer
systemctl enable --now borgpull@other-vps.timer
```

Each reads its config from `/etc/borgpull/hetzner.toml`, `/etc/borgpull/other-vps.toml`, etc.
